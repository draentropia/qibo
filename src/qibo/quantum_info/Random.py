from functools import reduce

import numpy as np

from qibo.config import MAX_ITERATIONS, PRECISION_TOL, raise_error
from qibo.quantum_info.utils import NUM_CLIFFORDS, ONEQUBIT_CLIFFORD_PARAMS


def random_gaussian_matrix(
    dims: int,
    rank: int = None,
    mean: float = None,
    stddev: float = None,
    seed: int = None,
):
    """Generates a random Gaussian Matrix.

    Gaussian matrices are matrices where each entry is
    sampled from a Gaussian probability distribution

    .. math::
        p(x) = \\frac{1}{\\sqrt{2 \\, \\pi} \\, \\sigma} \\, \\exp{-\\frac{(x - \\mu)^{2}}{2\\,\\sigma^{2}}}

    with mean :math:`\\mu` and standard deviation :math:`sigma`.

    Args:
        dims (int): dimension of the matrix.
        rank (int): rank of the matrix. If `None`, then `rank == dims`. Default: `None`.
        mean (float): mean of the Gaussian distribution.
        stddev (float): standard deviation of the Gaussian distribution.
        seed (int): Random seed used to initialize the pseudo-random number generator.
            Default: `None`.

    Returns:
        Random Gaussian matrix with dimensions `(dims, rank)`.

    """

    if dims <= 0:
        raise_error(ValueError, f"dims must be type int and positive.")

    if rank is None:
        rank = dims
    else:
        if rank > dims:
            raise_error(
                ValueError, f"rank ({rank}) cannot be greater than dims ({dims})."
            )
        elif rank <= 0:
            raise_error(ValueError, f"rank ({rank}) must be an int between 1 and dims.")

    if stddev is not None and stddev <= 0.0:
        raise_error(ValueError, f"stddev must be a positive float.")

    if seed is not None and not isinstance(seed, int):
        raise_error(TypeError, f"seed must be type int.")

    if mean is None:
        mean = 0
    if stddev is None:
        stddev = 1

    local_state = (
        np.random.RandomState(seed) if seed is not None else np.random.RandomState()
    )

    dims = (dims, rank)

    matrix = local_state.normal(
        loc=mean, scale=stddev, size=dims
    ) + 1.0j * local_state.normal(loc=mean, scale=stddev, size=dims)

    return matrix


def random_hermitian_operator(
    dims: int, semidefinite: bool = False, normalize: bool = False, seed: int = None
):
    """Generates a random Hermitian operator."""

    if dims <= 0:
        raise_error(ValueError, f"dims ({dims}) must be type int and positive.")

    if not isinstance(semidefinite, bool) or not isinstance(normalize, bool):
        raise_error(TypeError, f"semidefinite and normalize must be type bool.")

    if seed is not None and not isinstance(seed, int):
        raise_error(TypeError, f"seed must be type int.")

    local_state = (
        np.random.RandomState(seed) if seed is not None else np.random.RandomState()
    )

    operator = random_gaussian_matrix(dims, dims)

    if semidefinite:
        operator = np.dot(np.transpose(np.conj(operator)), operator)
    else:
        operator = (operator + np.transpose(np.conj(operator))) / 2

    if normalize:
        operator = operator / np.linalg.norm(operator)

    return operator


def random_unitary(dims: int, measure: str = "haar", seed: int = None):
    """."""

    if dims <= 0:
        raise_error(ValueError, f"dims must be type int and positive.")

    if measure is not None:
        if not isinstance(measure, str):
            raise_error(
                TypeError, f"measure must be type str but it is type {type(measure)}."
            )
        if measure != "haar":
            raise_error(ValueError, f"measure {measure} not implemented.")

    if seed is not None and not isinstance(seed, int):
        raise_error(TypeError, f"seed must be type int.")

    local_state = (
        np.random.RandomState(seed) if seed is not None else np.random.RandomState()
    )

    if measure == "haar":
        gaussian_matrix = random_gaussian_matrix(dims, dims)

        Q, R = np.linalg.qr(gaussian_matrix)
        D = np.diag(R)
        D = D / np.abs(D)
        R = np.diag(D)
        unitary = np.dot(Q, R)
    elif measure is None:
        from scipy.linalg import expm

        matrix_1 = local_state.randn(dims, dims)
        matrix_2 = local_state.randn(dims, dims)
        H = (matrix_1 + np.transpose(matrix_1)) + 1.0j * (
            matrix_2 - np.transpose(matrix_2.T)
        )
        unitary = expm(-1.0j * H / 2)

    return unitary


def random_statevector(dims: int, haar: bool = False, seed: int = None):
    """."""

    if dims <= 0:
        raise_error(ValueError, "dim must be of type int and >= 1")

    if not isinstance(haar, bool):
        raise_error(TypeError, f"haar must be type bool, but it is type {type(haar)}.")

    if seed is not None and not isinstance(seed, int):
        raise_error(TypeError, f"seed must be type int.")

    local_state = (
        np.random.RandomState(seed) if seed is not None else np.random.RandomState()
    )

    if not haar:
        probabilities = local_state.rand(dims)
        probabilities = probabilities / np.sum(probabilities)
        phases = 2 * np.pi * local_state.rand(dims)
        state = np.sqrt(probabilities) * np.exp(1.0j * phases)
    else:
        # select a random column of a haar random unitary
        k = local_state.randint(dims)
        state = random_unitary(dims, measure="haar")[:, k]

    return state


def random_density_matrix(
    dims,
    rank: int = None,
    pure: bool = False,
    method: str = "Hilbert-Schmidt",
    seed: int = None,
):
    """."""

    if dims <= 0:
        raise_error(ValueError, f"dims must be type int and positive.")

    if rank is not None and rank > dims:
        raise_error(ValueError, f"rank ({rank}) cannot be greater than dims ({dims}).")

    if rank is not None and rank <= 0:
        raise_error(ValueError, f"rank ({rank}) must be an int between 1 and dims.")

    if not isinstance(pure, bool):
        raise_error(TypeError, f"pure must be type bool, but it is type {type(pure)}.")

    if not isinstance(method, str):
        raise_error(
            TypeError, f"method must be type str, but it is type {type(method)}."
        )

    if seed is not None and not isinstance(seed, int):
        raise_error(TypeError, f"seed must be type int.")

    if pure:
        state = random_statevector(dims, seed=seed)
        state = np.outer(state, np.transpose(np.conj(state)))
    else:
        if method == "Hilbert-Schmidt":
            state = random_gaussian_matrix(dims, rank, seed=seed)
            state = np.dot(state, np.transpose(np.conj(state)))
            state = state / np.trace(state)
        elif method == "Bures":
            state = np.eye(dims) + random_unitary(dims, seed=seed)
            state = np.dot(state, random_gaussian_matrix(dims, rank, seed=seed))
            state = np.dot(state, np.transpose(np.conj(state)))
            state = state / np.trace(state)
        else:
            raise_error(ValueError, f"method {method} not found.")

    return state


def _clifford_unitary(phase, x, y, z):
    """Returns a parametrized single-qubit Clifford gate,
    where possible parameters are defined in
    `qibo.quantum_info.utils.ONEQUBIT_CLIFFORD_PARAMS`.

    """

    return np.array(
        [
            [
                np.cos(phase / 2) - 1.0j * z * np.sin(phase / 2),
                -y * np.sin(phase / 2) - 1.0j * x * np.sin(phase / 2),
            ],
            [
                y * np.sin(phase / 2) - 1.0j * x * np.sin(phase / 2),
                np.cos(phase / 2) + 1.0j * z * np.sin(phase / 2),
            ],
        ]
    )


def random_clifford_gate(qubits, return_circuit: bool = False, seed: int = None):
    """."""

    if (
        not isinstance(qubits, int)
        and not isinstance(qubits, list)
        and not isinstance(qubits, np.ndarray)
    ):
        raise_error(
            TypeError,
            f"qubits must be either type int, list or ndarray, but it is type {type(qubits)}.",
        )

    if isinstance(qubits, int) and qubits <= 0:
        raise_error(ValueError, f"qubits must be a positive integer.")

    if (isinstance(qubits, list) or isinstance(qubits, np.ndarray)) and any(
        q < 0 for q in qubits
    ):
        raise_error(ValueError, f"qubit indexes must be non-negative integers.")

    if not isinstance(return_circuit, bool):
        raise_error(
            TypeError,
            f"return_circuit must be type bool, but it is type {type(return_circuit)}.",
        )

    if seed is not None and not isinstance(seed, int):
        raise_error(TypeError, f"seed must be type int.")

    local_state = (
        np.random.RandomState(seed=seed)
        if seed is not None
        else np.random.RandomState()
    )

    if isinstance(qubits, int):
        qubits = range(qubits)

    parameters = local_state.randint(0, NUM_CLIFFORDS, len(qubits))

    unitaries = [_clifford_unitary(*ONEQUBIT_CLIFFORD_PARAMS[p]) for p in parameters]

    if return_circuit == True:
        from qibo import gates

        # tensor product of all gates generated
        unitaries = reduce(np.kron, unitaries)

        unitaries = gates.Unitary(unitaries, *qubits)
    else:
        unitaries = np.array(unitaries) if len(unitaries) > 1 else unitaries[0]

    return unitaries


def random_stochastic_matrix(
    dims: int,
    bistochastic: bool = False,
    precision_tol: float = None,
    max_iterations: int = None,
    seed: int = None,
):
    """."""
    if dims <= 0:
        raise_error(ValueError, f"dims must be type int and positive.")

    if not isinstance(bistochastic, bool):
        raise_error(
            TypeError,
            f"bistochastic must be type bool, but it is type {type(bistochastic)}.",
        )

    if precision_tol is not None:
        if not isinstance(precision_tol, float):
            raise_error(
                TypeError,
                f"precision_tol must be type float, but it is type {type(precision_tol)}.",
            )
        if precision_tol < 0.0:
            raise_error(ValueError, f"precision_tol must be non-negative.")

    if max_iterations is not None:
        if not isinstance(max_iterations, int):
            raise_error(
                TypeError,
                f"max_iterations must be type int, but it is type {type(precision_tol)}.",
            )
        if max_iterations <= 0.0:
            raise_error(ValueError, f"max_iterations must be a positive int.")

    if seed is not None and not isinstance(seed, int):
        raise_error(TypeError, f"seed must be type int.")

    local_state = (
        np.random.RandomState(seed) if seed is not None else np.random.RandomState()
    )

    if precision_tol is None:
        precision_tol = PRECISION_TOL
    if max_iterations is None:
        max_iterations = MAX_ITERATIONS

    matrix = local_state.rand(dims, dims)
    row_sum = matrix.sum(axis=1)

    if bistochastic:
        column_sum = matrix.sum(axis=0)
        count = 0
        while count <= max_iterations - 1 and (
            (
                np.any(row_sum >= 1 + precision_tol)
                or np.any(row_sum <= 1 - precision_tol)
            )
            or (
                np.any(column_sum >= 1 + precision_tol)
                or np.any(column_sum <= 1 - precision_tol)
            )
        ):
            matrix = matrix / matrix.sum(axis=0)
            matrix = matrix / matrix.sum(axis=1)[:, np.newaxis]
            row_sum = matrix.sum(axis=1)
            column_sum = matrix.sum(axis=0)
            count += 1
        if count == max_iterations:
            import warnings

            warnings.warn("Reached max iterations.", RuntimeWarning)
    else:
        matrix = matrix / np.outer(row_sum, [1] * dims)

    return matrix
