from collections import Counter
from functools import reduce

import numpy as np
import pytest

from qibo import Circuit, gates
from qibo.backends import CliffordBackend, TensorflowBackend
from qibo.quantum_info._clifford_utils import (
    _cnot_cost,
    _one_qubit_paulis_string_product,
    _string_product,
)
from qibo.quantum_info.clifford import Clifford
from qibo.quantum_info.random_ensembles import random_clifford


def construct_clifford_backend(backend):
    if isinstance(backend, TensorflowBackend):
        with pytest.raises(NotImplementedError) as excinfo:
            clifford_backend = CliffordBackend(backend)
            assert (
                str(excinfo.value)
                == "TensorflowBackend for Clifford Simulation is not supported yet."
            )
    else:
        return CliffordBackend(backend)


@pytest.mark.parametrize("nqubits", [2, 10, 50, 100])
def test_clifford_from_symplectic_matrix(backend, nqubits):
    if isinstance(backend, TensorflowBackend):
        with pytest.raises(NotImplementedError):
            clifford_backend = CliffordBackend(backend)
    else:
        clifford_backend = CliffordBackend(backend)
        symplectic_matrix = clifford_backend.zero_state(nqubits)
        clifford_1 = Clifford(symplectic_matrix, engine=backend)
        clifford_2 = Clifford(symplectic_matrix[:-1], engine=backend)

        for clifford in [clifford_1, clifford_2]:
            backend.assert_allclose(
                clifford.symplectic_matrix.shape,
                (2 * nqubits + 1, 2 * nqubits + 1),
            )


@pytest.mark.parametrize("measurement", [False, True])
def test_clifford_from_circuit(backend, measurement):
    clifford_backend = construct_clifford_backend(backend)
    if not clifford_backend:
        return

    c = random_clifford(3, backend=backend)
    if measurement:
        c.add(gates.M(*np.random.choice(3, size=2, replace=False)))

    result = clifford_backend.execute_circuit(c)
    obj = Clifford.from_circuit(c, engine=backend)
    backend.assert_allclose(obj.state(), result.state())
    if measurement:
        backend.assert_allclose(obj.probabilities(), result.probabilities())


@pytest.mark.parametrize("algorithm", ["AG04", "BM20"])
@pytest.mark.parametrize("nqubits", [1, 2, 3, 10, 50])
def test_clifford_to_circuit(backend, nqubits, algorithm):
    if backend.__class__.__name__ == "TensorflowBackend":
        pytest.skip("CliffordBackend not defined for Tensorflow engine.")

    clifford = random_clifford(nqubits, backend=backend)

    symplectic_matrix_original = Clifford.from_circuit(
        clifford, engine=backend
    ).symplectic_matrix

    symplectic_matrix_from_symplectic = Clifford(
        symplectic_matrix_original, engine=backend
    )

    symplectic_matrix_compiled = Clifford.from_circuit(clifford, engine=backend)

    if algorithm == "BM20" and nqubits > 3:
        with pytest.raises(ValueError):
            symplectic_matrix_compiled = symplectic_matrix_compiled.to_circuit(
                algorithm=algorithm
            )
        with pytest.raises(ValueError):
            _cnot_cost(symplectic_matrix_compiled)
    else:
        with pytest.raises(TypeError):
            symplectic_matrix_compiled.to_circuit(algorithm=True)
        with pytest.raises(ValueError):
            symplectic_matrix_compiled.to_circuit(algorithm="BM21")

        symplectic_matrix_from_symplectic = (
            symplectic_matrix_from_symplectic.to_circuit(algorithm=algorithm)
        )
        symplectic_matrix_from_symplectic = Clifford.from_circuit(
            symplectic_matrix_from_symplectic, engine=backend
        ).symplectic_matrix

        symplectic_matrix_compiled = symplectic_matrix_compiled.to_circuit(
            algorithm=algorithm
        )
        symplectic_matrix_compiled = Clifford.from_circuit(
            symplectic_matrix_compiled, engine=backend
        ).symplectic_matrix

        backend.assert_allclose(
            symplectic_matrix_from_symplectic, symplectic_matrix_original
        )
        backend.assert_allclose(symplectic_matrix_compiled, symplectic_matrix_original)


@pytest.mark.parametrize("nqubits", [1, 10, 50])
def test_clifford_initialization(backend, nqubits):
    if backend.__class__.__name__ == "TensorflowBackend":
        pytest.skip("CliffordBackend not defined for Tensorflow engine.")

    clifford_backend = construct_clifford_backend(backend)

    circuit = random_clifford(nqubits, backend=backend)
    symplectic_matrix = clifford_backend.execute_circuit(circuit).symplectic_matrix

    clifford_from_symplectic = Clifford(symplectic_matrix, engine=backend)
    clifford_from_circuit = Clifford.from_circuit(circuit, engine=backend)
    clifford_from_initialization = Clifford(circuit, engine=backend)

    backend.assert_allclose(
        clifford_from_symplectic.symplectic_matrix, symplectic_matrix
    )
    backend.assert_allclose(clifford_from_circuit.symplectic_matrix, symplectic_matrix)
    backend.assert_allclose(
        clifford_from_initialization.symplectic_matrix, symplectic_matrix
    )


@pytest.mark.parametrize("return_array", [True, False])
@pytest.mark.parametrize("symplectic", [True, False])
def test_clifford_stabilizers(backend, symplectic, return_array):
    clifford_backend = construct_clifford_backend(backend)
    if not clifford_backend:
        return

    nqubits = 3
    c = Circuit(nqubits)
    c.add(gates.X(2))
    c.add(gates.H(0))
    obj = Clifford.from_circuit(c, engine=backend)
    if return_array:
        true_generators = [
            reduce(np.kron, [getattr(gates, gate)(0).matrix() for gate in generator])
            for generator in ["XII", "IZI", "IIZ"]
        ]
    else:
        true_generators = ["XII", "IZI", "IIZ"]
    true_phases = [1, 1, -1]
    generators, phases = obj.generators(return_array=return_array)

    if return_array:
        backend.assert_allclose(generators[3:], true_generators)
        backend.assert_allclose(phases.tolist()[3:], true_phases)
    else:
        assert generators[3:] == true_generators
        assert phases.tolist()[3:] == true_phases

    if symplectic:
        true_stabilizers = obj.symplectic_matrix[nqubits:-1, :]
    elif not symplectic and return_array:
        true_stabilizers = []
        for stab in [
            "-XZZ",
            "XZI",
            "-XIZ",
            "XII",
            "-IZZ",
            "IZI",
            "-IIZ",
            "III",
        ]:
            tmp = reduce(
                np.kron, [getattr(gates, s)(0).matrix() for s in stab.replace("-", "")]
            )
            if "-" in stab:
                tmp *= -1
            true_stabilizers.append(tmp)
    elif not symplectic and not return_array:
        true_stabilizers = [
            "-XZZ",
            "XZI",
            "-XIZ",
            "XII",
            "-IZZ",
            "IZI",
            "-IIZ",
            "III",
        ]

    stabilizers = obj.stabilizers(symplectic, return_array)
    if symplectic or (not symplectic and return_array):
        backend.assert_allclose(stabilizers, true_stabilizers)
    else:
        assert stabilizers, true_stabilizers


@pytest.mark.parametrize("return_array", [True, False])
@pytest.mark.parametrize("symplectic", [True, False])
def test_clifford_destabilizers(backend, symplectic, return_array):
    clifford_backend = construct_clifford_backend(backend)
    if not clifford_backend:
        return

    nqubits = 3
    c = Circuit(nqubits)
    c.add(gates.X(2))
    c.add(gates.H(0))
    obj = Clifford.from_circuit(c, engine=backend)
    if return_array:
        true_generators = [
            reduce(np.kron, [getattr(gates, gate)(0).matrix() for gate in generator])
            for generator in ["ZII", "IXI", "IIX"]
        ]
        true_generators = backend.cast(true_generators)
    else:
        true_generators = ["ZII", "IXI", "IIX"]
    true_phases = [1, 1, 1]
    generators, phases = obj.generators(return_array=return_array)

    if return_array:
        backend.assert_allclose(generators[:3], true_generators)
        backend.assert_allclose(phases.tolist()[:3], true_phases)
    else:
        assert generators[:3] == true_generators
        assert phases.tolist()[:3] == true_phases

    if symplectic:
        true_destabilizers = obj.symplectic_matrix[:nqubits, :]
    elif not symplectic and return_array:
        true_destabilizers = []
        for destab in [
            "ZXX",
            "ZXI",
            "ZIX",
            "ZII",
            "IXX",
            "IXI",
            "IIX",
            "III",
        ]:
            tmp = reduce(
                np.kron,
                [getattr(gates, s)(0).matrix() for s in destab.replace("-", "")],
            )
            if "-" in destab:
                tmp *= -1
            true_destabilizers.append(tmp)
    elif not symplectic and not return_array:
        true_destabilizers = [
            "ZXX",
            "ZXI",
            "ZIX",
            "ZII",
            "IXX",
            "IXI",
            "IIX",
            "III",
        ]
    destabilizers = obj.destabilizers(symplectic, return_array)
    if symplectic or (not symplectic and return_array):
        backend.assert_allclose(destabilizers, true_destabilizers)
    else:
        assert destabilizers, true_destabilizers


@pytest.mark.parametrize("binary", [True, False])
def test_clifford_samples_frequencies(backend, binary):
    clifford_backend = construct_clifford_backend(backend)
    if not clifford_backend:
        return
    c = random_clifford(5)
    c.add(gates.M(3, register_name="3"))
    c.add(gates.M(0, 1, register_name="01"))
    obj = Clifford.from_circuit(c, nshots=50, engine=backend)
    samples_1 = obj.samples(binary=binary, registers=True)
    samples_2 = obj.samples(binary=binary, registers=False)
    if binary:
        backend.assert_allclose(samples_2, np.hstack((samples_1["3"], samples_1["01"])))
    else:
        backend.assert_allclose(
            samples_2, [s1 + 4 * s2 for s1, s2 in zip(samples_1["01"], samples_1["3"])]
        )
    freq_1 = obj.frequencies(binary=binary, registers=True)
    freq_2 = obj.frequencies(binary=binary, registers=False)

    if not binary:
        freq_1 = {
            reg: Counter({f"{int(k):0{len(reg)}b}": v for k, v in freq.items()})
            for reg, freq in freq_1.items()
        }
        freq_2 = Counter({f"{int(k):03b}": v for k, v in freq_2.items()})

    for register, counter in freq_1.items():
        for bits_1, freq in counter.items():
            tot = 0
            for bits_2, counts in freq_2.items():
                flag = bits_1 == bits_2[0] if register == "3" else bits_1 == bits_2[1:]
                if flag:
                    tot += counts
            backend.assert_allclose(freq, tot)


def test_clifford_samples_error(backend):
    c = random_clifford(1, backend=backend)
    if isinstance(backend, TensorflowBackend):
        with pytest.raises(NotImplementedError):
            clifford_backend = CliffordBackend(backend)
    else:
        obj = Clifford.from_circuit(c, engine=backend)
        with pytest.raises(RuntimeError) as excinfo:
            obj.samples()
            assert str(excinfo.value) == "No measurement provided."


@pytest.mark.parametrize("deep", [False, True])
@pytest.mark.parametrize("nqubits", [1, 10, 100])
def test_clifford_copy(backend, nqubits, deep):
    if backend.__class__.__name__ == "TensorflowBackend":
        pytest.skip("CliffordBackend not defined for Tensorflow engine.")

    circuit = random_clifford(nqubits, backend=backend)
    clifford = Clifford.from_circuit(circuit, engine=backend)

    with pytest.raises(TypeError):
        clifford.copy(deep="True")

    copy = clifford.copy(deep=deep)

    backend.assert_allclose(copy.symplectic_matrix, clifford.symplectic_matrix)
    assert copy.nqubits == clifford.nqubits
    assert copy.measurements == clifford.measurements
    assert copy.nshots == clifford.nshots
    assert copy.engine == clifford.engine


@pytest.mark.parametrize("pauli_2", ["Z", "Y", "Y"])
@pytest.mark.parametrize("pauli_1", ["X", "Y", "Z"])
def test_one_qubit_paulis_string_product(backend, pauli_1, pauli_2):
    products = {
        "XY": "iZ",
        "YZ": "iX",
        "ZX": "iY",
        "YX": "-iZ",
        "ZY": "-iX",
        "XZ": "iY",
        "XX": "I",
        "ZZ": "I",
        "YY": "I",
        "XI": "X",
        "IX": "X",
        "YI": "Y",
        "IY": "Y",
        "ZI": "Z",
        "IZ": "Z",
    }

    product = _one_qubit_paulis_string_product(pauli_1, pauli_2)
    product_target = products[pauli_1 + pauli_2]

    assert product == product_target


@pytest.mark.parametrize(
    ["operators", "target"],
    [
        [["X", "Y", "Z"], "iI"],
        [["Z", "X", "Y", "X", "Z"], "-Y"],
        [["Z", "I", "Z"], "I"],
        [["Y", "X"], "-iZ"],
        [["iY", "iX"], "iZ"],
    ],
)
def test_string_product(backend, operators, target):
    product = _string_product(operators)
    assert product == target


def test_1q_paulis_string_product():
    assert "-iZ" == _one_qubit_paulis_string_product("iX", "iY")
