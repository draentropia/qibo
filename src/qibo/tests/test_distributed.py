import pytest
import numpy as np
import qibo
from qibo import models, gates


def random_state(nqubits):
    shape = (2 ** nqubits,)
    x = np.random.random(shape) + 1j * np.random.random(shape)
    x = x / np.sqrt((np.abs(x) ** 2).sum())
    return x


def check_device_queues(queues):
    """Asserts that global qubits do not collide with the gates to be applied."""
    for gate_group in queues.queues:
        for device_gates in gate_group:
            target_qubits = set()
            for gate in device_gates:
                target_qubits |= set(gate.original_gate.target_qubits)
            assert not queues.global_qubits_set & target_qubits


def test_invalid_devices():
    """Check if error is raised if total devices is not a power of 2."""
    devices = {"/GPU:0": 2, "/GPU:1": 1}
    with pytest.raises(ValueError):
        c = models.DistributedCircuit(4, devices)


def test_ndevices():
    """Check that ``ndevices`` and ``nglobal`` is set properly."""
    devices = {"/GPU:0": 2, "/GPU:1": 2}
    c = models.DistributedCircuit(5, devices)
    assert c.ndevices == 4
    assert c.nglobal == 2


def test_set_gates_simple():
    devices = {"/GPU:0": 2, "/GPU:1": 2}
    c = models.DistributedCircuit(6, devices)
    c.add((gates.H(i) for i in range(4)))
    c.global_qubits = [4, 5]
    c.set_gates()

    check_device_queues(c.queues)
    assert len(c.queues.queues) == 1
    assert len(c.queues.queues[0]) == 4
    for queues in c.queues.queues[0]:
        assert len(queues) == 4


def test_set_gates_with_global_swap():
    devices = {"/GPU:0": 2, "/GPU:1": 2}
    c = models.DistributedCircuit(6, devices)
    c.add([gates.H(0), gates.H(2), gates.H(3)])
    c.add(gates.SWAP(3, 4))
    c.add([gates.X(1), gates.X(2)])
    c.global_qubits = [4, 5]
    c.set_gates()

    check_device_queues(c.queues)
    assert len(c.queues.special_queue) == 1
    assert len(c.queues.queues) == 3
    assert len(c.queues.queues[0]) == 4
    assert len(c.queues.queues[1]) == 0
    assert len(c.queues.queues[2]) == 4
    for device_group in c.queues.queues[0]:
        assert len(device_group) == 3
    for device_group in c.queues.queues[2]:
        assert len(device_group) == 2


def test_transform_queue_simple():
    qibo.set_backend("custom")
    devices = {"/GPU:0": 1, "/GPU:1": 1}
    c = models.DistributedCircuit(4, devices)
    c.add((gates.H(i) for i in range(4)))
    c.global_qubits = [0]
    tqueue = c.queues.transform(c.queue)
    assert len(tqueue) == 6
    for i in range(3):
        assert isinstance(tqueue[i], gates.H)
        assert tqueue[i].target_qubits == (i + 1,)
    assert isinstance(tqueue[3], gates.SWAP)
    assert tqueue[3].target_qubits == (0, 1)
    assert isinstance(tqueue[4], gates.H)
    assert tqueue[4].target_qubits == (1,)
    assert isinstance(tqueue[5], gates.SWAP)
    assert tqueue[5].target_qubits == (0, 1)


def test_transform_queue_more_gates():
    qibo.set_backend("custom")
    devices = {"/GPU:0": 2, "/GPU:1": 2}
    c = models.DistributedCircuit(4, devices)
    c.add(gates.H(0))
    c.add(gates.H(1))
    c.add(gates.CNOT(2, 3))
    c.add(gates.CZ(0, 1))
    c.add(gates.CNOT(3, 0))
    c.add(gates.CNOT(1, 2))
    c.global_qubits = [2, 3]
    tqueue = c.queues.transform(c.queue)

    assert len(tqueue) == 10
    assert isinstance(tqueue[0], gates.H)
    assert tqueue[0].target_qubits == (0,)
    assert isinstance(tqueue[1], gates.H)
    assert tqueue[1].target_qubits == (1,)
    assert isinstance(tqueue[2], gates.CZ)
    assert tqueue[2].target_qubits == (1,)
    assert isinstance(tqueue[3], gates.SWAP)
    assert set(tqueue[3].target_qubits) == {1, 3}
    assert isinstance(tqueue[4], gates.CNOT)
    assert tqueue[4].target_qubits == (1,)
    assert isinstance(tqueue[5], gates.CNOT)
    assert tqueue[5].target_qubits == (0,)
    assert isinstance(tqueue[6], gates.SWAP)
    assert set(tqueue[6].target_qubits) == {0, 2}
    assert isinstance(tqueue[7], gates.CNOT)
    assert tqueue[7].target_qubits == (0,)
    assert isinstance(tqueue[8], gates.SWAP)
    assert set(tqueue[8].target_qubits) == {0, 2}
    assert isinstance(tqueue[9], gates.SWAP)
    assert set(tqueue[9].target_qubits) == {1, 3}

# FIXME: Unskip this test
@pytest.mark.skip
def test_set_gates_controlled():
    devices = {"/GPU:0": 2, "/GPU:1": 2}
    c = models.DistributedCircuit(6, devices)
    c.add([gates.H(0), gates.H(2), gates.H(3)])
    c.add(gates.CNOT(4, 5))
    c.add(gates.Z(1).controlled_by(0))
    c.add(gates.SWAP(2, 3))
    c.add([gates.X(2), gates.X(3), gates.X(4)])
    c.set_gates()

    assert c.queues.global_qubits_lists == [[1, 4], [0, 5]]
    check_device_queues(c.queues)
    print(c.queues.global_qubits_lists)
    for i, queue in enumerate(c.queues.queues):
        assert len(queue) == 2
        assert len(queue[0]) == 3 + (i % 2)
        assert len(queue[1]) == 4 + (i > 1)


def test_default_initialization():
    devices = {"/GPU:0": 2, "/GPU:1": 2}
    c = models.DistributedCircuit(6, devices)
    c._cast_initial_state()
    assert c.global_qubits == [0, 1]

    final_state = c.final_state.numpy()
    target_state = np.zeros_like(final_state)
    target_state[0] = 1
    np.testing.assert_allclose(target_state, final_state)


@pytest.mark.parametrize("nqubits", [5, 6])
def test_user_initialization(nqubits):
    import itertools
    target_state = random_state(nqubits)

    devices = {"/GPU:0": 2, "/GPU:1": 2}
    c = models.DistributedCircuit(nqubits, devices)
    c._cast_initial_state(target_state)

    final_state = c.final_state.numpy()
    np.testing.assert_allclose(target_state, final_state)

    target_state = target_state.reshape(nqubits * (2,))
    for i, s in enumerate(itertools.product([0, 1], repeat=c.nglobal)):
        piece = c.pieces[i].numpy()
        target_piece = target_state[s]
        np.testing.assert_allclose(target_piece.ravel(), piece)


def test_distributed_circuit_errors():
    devices = {"/GPU:0": 2, "/GPU:1": 2}
    c = models.Circuit(6, devices)
    # Access global qubits before setting them
    with pytest.raises(ValueError):
        global_qubits = c.global_qubits
    # Attempt to set wrong number of global qubits
    with pytest.raises(ValueError):
        c.global_qubits = [1, 2, 3]
    # Attempt to set gates before adding any gate
    with pytest.raises(RuntimeError):
        c.set_gates()
    # Attempt to access state before being set
    with pytest.raises(RuntimeError):
        final_state = c.final_state
    # Attempt to add gate so that available global qubits are not enough
    small_c = models.Circuit(2, {"/GPU:0": 2})
    with pytest.raises(ValueError):
        small_c.add(gates.SWAP(0, 1))
    # Attempt to compile
    with pytest.raises(RuntimeError):
        c.compile()
    # Attempt to use ``.with_noise``
    with pytest.raises(NotImplementedError):
        noisy_c = c.with_noise((0.1, 0.2, 0.1))


@pytest.mark.parametrize("ndevices", [2, 4, 8])
def test_simple_execution(ndevices):
    qibo.set_backend("custom")
    devices = {"/GPU:0": ndevices // 2, "/GPU:1": ndevices // 2}

    dist_c = models.DistributedCircuit(6, devices)
    dist_c.add((gates.H(i) for i in range(dist_c.nlocal)))
    dist_c.global_qubits = range(dist_c.nlocal, dist_c.nqubits)

    c = models.Circuit(6)
    c.add((gates.H(i) for i in range(dist_c.nlocal)))

    initial_state = random_state(c.nqubits)
    final_state = dist_c(np.copy(initial_state)).numpy()
    target_state = c(np.copy(initial_state)).numpy()
    np.testing.assert_allclose(target_state, final_state)


@pytest.mark.parametrize("ndevices", [2, 4, 8])
def test_simple_execution_global(ndevices):
    qibo.set_backend("custom")
    devices = {"/GPU:0": ndevices // 2, "/GPU:1": ndevices // 2}

    dist_c = models.DistributedCircuit(6, devices)
    dist_c.add((gates.H(i) for i in range(6)))

    c = models.Circuit(6)
    c.add((gates.H(i) for i in range(6)))

    initial_state = random_state(c.nqubits)
    final_state = dist_c(np.copy(initial_state)).numpy()
    target_state = c(np.copy(initial_state)).numpy()
    np.testing.assert_allclose(target_state, final_state)


@pytest.mark.parametrize("ndevices", [2, 4, 8])
def test_execution_special_gate(ndevices):
    qibo.set_backend("custom")
    devices = {"/GPU:0": ndevices // 2, "/GPU:1": ndevices // 2}

    dist_c = models.DistributedCircuit(6, devices)
    initial_state = random_state(dist_c.nqubits)
    dist_c.add(gates.Flatten(np.copy(initial_state)))
    dist_c.add((gates.H(i) for i in range(dist_c.nlocal)))
    dist_c.global_qubits = range(dist_c.nlocal, dist_c.nqubits)

    c = models.Circuit(6)
    c.add(gates.Flatten(np.copy(initial_state)))
    c.add((gates.H(i) for i in range(dist_c.nlocal)))

    final_state = dist_c().numpy()
    target_state = c().numpy()
    np.testing.assert_allclose(target_state, final_state)


@pytest.mark.parametrize("ndevices", [2, 4])
def test_controlled_execution(ndevices):
    qibo.set_backend("custom")
    devices = {"/GPU:0": ndevices}
    dist_c = models.DistributedCircuit(4, devices)
    dist_c.add((gates.H(i) for i in range(dist_c.nglobal, 4)))
    dist_c.add(gates.CNOT(0, 2))

    c = models.Circuit(4)
    c.add((gates.H(i) for i in range(dist_c.nglobal, 4)))
    c.add(gates.CNOT(0, 2))

    initial_state = random_state(c.nqubits)
    final_state = dist_c(np.copy(initial_state)).numpy()
    target_state = c(np.copy(initial_state)).numpy()
    np.testing.assert_allclose(target_state, final_state)


@pytest.mark.parametrize("ndevices", [2, 4])
def test_execution_with_swap_global(ndevices):
    qibo.set_backend("custom")
    devices = {"/GPU:0": ndevices // 2, "/GPU:1": ndevices // 2}
    dist_c = models.DistributedCircuit(4, devices)
    dist_c.add((gates.H(i) for i in range(dist_c.nglobal, 4)))
    dist_c.add(gates.SWAP(0, 2))
    dist_c.add((gates.H(i) for i in range(dist_c.nglobal, 4)))

    c = models.Circuit(4)
    c.add((gates.H(i) for i in range(dist_c.nglobal, 4)))
    c.add(gates.SWAP(0, 2))
    c.add((gates.H(i) for i in range(dist_c.nglobal, 4)))

    initial_state = random_state(c.nqubits)
    final_state = dist_c(np.copy(initial_state)).numpy()
    target_state = c(np.copy(initial_state)).numpy()
    np.testing.assert_allclose(target_state, final_state)


def test_distributed_circuit_addition():
    # Attempt to add circuits with different devices
    qibo.set_backend("custom")
    devices = {"/GPU:0": 2, "/GPU:1": 2}
    c1 = models.DistributedCircuit(6, devices)
    c2 = models.DistributedCircuit(6, {"/GPU:0": 2})
    with pytest.raises(ValueError):
        c = c1 + c2

    c2 = models.DistributedCircuit(6, devices)
    c1.add([gates.H(i) for i in range(6)])
    c2.add([gates.CNOT(i, i + 1) for i in range(5)])
    c2.add([gates.Z(i) for i in range(6)])
    dist_c = c1 + c2

    c = models.Circuit(6)
    c.add([gates.H(i) for i in range(6)])
    c.add([gates.CNOT(i, i + 1) for i in range(5)])
    c.add([gates.Z(i) for i in range(6)])

    target_state = c().numpy()
    final_state = dist_c().numpy()
    assert c.depth == dist_c.depth
    np.testing.assert_allclose(target_state, final_state)


@pytest.mark.skip("Global qubits do not change in the SWAP gate implementation.")
@pytest.mark.parametrize("nqubits", [7, 8, 9, 10, 30, 31, 32, 33])
@pytest.mark.parametrize("ndevices", [2, 4])
def test_distributed_qft_global_qubits(nqubits, ndevices):
    """Check that the generated global qubit list is the expected for QFT."""
    c = models.QFT(nqubits, accelerators={"/GPU:0": ndevices})
    c.set_gates()

    check_device_queues(c.queues)
    nglobal = c.nglobal
    if nglobal > 2:
        raise NotImplementedError
    if nqubits % 2 and nglobal == 1:
      target_global_qubits = [[nqubits - 1], [nqubits // 2]]
    else:
        target_global_qubits = [list(range(nqubits - nglobal, nqubits)),
                                list(range(nglobal)),
                                list(range(nglobal, 2 * nglobal))]
    assert target_global_qubits == c.queues.global_qubits_lists


@pytest.mark.parametrize("nqubits", [28, 29, 30, 31, 32, 33, 34])
@pytest.mark.parametrize("ndevices", [2, 4, 8, 16, 32, 64])
def test_distributed_qft_global_qubits_validity(nqubits, ndevices):
    """Check that no gates are applied to global qubits for practical QFT cases."""
    c = models.QFT(nqubits, accelerators={"/GPU:0": ndevices})
    c.set_gates()
    check_device_queues(c.queues)


@pytest.mark.parametrize("nqubits", [7, 8, 12, 13])
@pytest.mark.parametrize("accelerators",
                         [{"/GPU:0": 2},
                          {"/GPU:0": 2, "/GPU:1": 2},
                          {"/GPU:0": 2, "/GPU:1": 5, "/GPU:2": 1}])
def test_distributed_qft_execution(nqubits, accelerators):
    qibo.set_backend("custom")
    dist_c = models.QFT(nqubits, accelerators=accelerators)
    c = models.QFT(nqubits)

    initial_state = random_state(nqubits)
    final_state = dist_c(initial_state).numpy()
    target_state = c(initial_state).numpy()
    np.testing.assert_allclose(target_state, final_state)
