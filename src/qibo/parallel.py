"""
Resources for parallel circuit evaluation.
"""


class ParallelResources:  # pragma: no cover
    """Auxiliary singleton class for sharing memory objects in a
    multiprocessing environment when performing a parallel evaluations.

    This class takes care of duplicating resources for each process
    and calling the respective loss function.
    """
    import sys
    import multiprocessing as mp

    # private objects holding the state
    _instance = None
    # dict with of shared objects
    _objects_per_process = {}
    custom_function = None
    lock = None
    arguments = ()

    def __new__(cls, *args, **kwargs):
        """Creates singleton instance."""
        if cls._instance is None:
            cls._instance = super(ParallelResources, cls).__new__(
                cls, *args, **kwargs)
            if cls.sys.platform == 'win32' or cls.sys.platform == 'darwin':  # pragma: no cover
                from qibo.config import raise_error
                raise_error(NotImplementedError,
                            "Parallel evaluation supported only on linux.")
        return cls._instance

    def run(self, params=None):
        """Evaluates the custom_function object for a specific set of
        parameters. This class performs the lock mechanism to duplicate objects
        for each process.
        """
        # lock to avoid race conditions
        self.lock.acquire()
        # get process name
        pname = self.mp.current_process().name
        # check if there are objects already stored
        args = self._objects_per_process.get(pname, None)
        if args is None:
            args = []
            for obj in self.arguments:
                try:
                    # copy object if copy method is available
                    copy = obj.copy(deep=True)
                except (TypeError, AttributeError):
                    # if copy is not implemented just use the original object
                    copy = obj
                except Exception as e:
                    # use print otherwise the message will not appear # CodeText:skip
                    print('Exception in ParallelResources',
                          str(e))  # CodeText:skip
                args.append(copy)
            args = tuple(args)
            self._objects_per_process[pname] = args
        # unlock
        self.lock.release()
        # finally compute the custom function
        return self.custom_function(params, *args)

    def reset(self):
        """Cleanup memory."""
        self._objects_per_process = {}
        self.custom_function = None
        self.lock = None
        self.arguments = ()


def _executor(params):  # pragma: no cover
    """Executes singleton call."""
    return ParallelResources().run(params)


def parallel_execution(circuit, states, processes=None, backend=None):
    """Execute circuit for multiple states.

    Example:
        .. code-block:: python

            import qibo
            original_backend = qibo.get_backend()
            qibo.set_backend('qibojit')
            from qibo import models, set_threads
            from qibo.parallel import parallel_execution
            import numpy as np
            # create circuit
            nqubits = 22
            circuit = models.QFT(nqubits)
            # create random states
            states = [ np.random.random(2**nqubits) for i in range(5)]
            # set threads to 1 per process (optional, requires tuning)
            set_threads(1)
            # execute in parallel
            results = parallel_execution(circuit, states, processes=2)
            qibo.set_backend(original_backend)

    Args:
        circuit (qibo.models.Circuit): the input circuit.
        states (list): list of states for the circuit evaluation.
        processes (int): number of processes for parallel evaluation.

    Returns:
        Circuit evaluation for input states.
    """
    if backend is None:
        from qibo.backends import GlobalBackend
        backend = GlobalBackend()

    if states is None or not isinstance(states, list):
        from qibo.config import raise_error
        raise_error(RuntimeError, "states must be a list.")

    def operation(state, circuit):
        return backend.execute_circuit(circuit, state)

    from joblib import Parallel, delayed
    results = Parallel(n_jobs=processes, prefer='threads')(
        delayed(operation)(state, circuit) for state in states)

    return results


def parallel_parametrized_execution(circuit, parameters, initial_state=None, processes=None, backend=None):
    """Execute circuit for multiple parameters and fixed initial_state.

    Example:
        .. code-block:: python

            import qibo
            original_backend = qibo.get_backend()
            qibo.set_backend('qibojit')
            from qibo import models, gates, set_threads
            from qibo.parallel import parallel_parametrized_execution
            import numpy as np
            # create circuit
            nqubits = 6
            nlayers = 2
            circuit = models.Circuit(nqubits)
            for l in range(nlayers):
                circuit.add((gates.RY(q, theta=0) for q in range(nqubits)))
                circuit.add((gates.CZ(q, q+1) for q in range(0, nqubits-1, 2)))
                circuit.add((gates.RY(q, theta=0) for q in range(nqubits)))
                circuit.add((gates.CZ(q, q+1) for q in range(1, nqubits-2, 2)))
                circuit.add(gates.CZ(0, nqubits-1))
            circuit.add((gates.RY(q, theta=0) for q in range(nqubits)))
            # create random parameters
            size = len(circuit.get_parameters())
            parameters = [ np.random.uniform(0, 2*np.pi, size) for _ in range(10) ]
            # set threads to 1 per process (optional, requires tuning)
            set_threads(1)
            # execute in parallel
            results = parallel_parametrized_execution(circuit, parameters, processes=2)
            qibo.set_backend(original_backend)

    Args:
        circuit (qibo.models.Circuit): the input circuit.
        parameters (list): list of parameters for the circuit evaluation.
        initial_state (np.array): initial state for the circuit evaluation.
        processes (int): number of processes for parallel evaluation.

    Returns:
        Circuit evaluation for input parameters.
    """
    if backend is None:
        from qibo.backends import GlobalBackend
        backend = GlobalBackend()

    if not isinstance(parameters, list):
        from qibo.config import raise_error
        raise_error(RuntimeError, "parameters must be a list.")

    def operation(params, circuit, state):
        if state is not None:
            state = backend.cast(state)
        circuit.set_parameters(params)
        return backend.execute_circuit(circuit, state)

    from joblib import Parallel, delayed
    results = Parallel(n_jobs=processes, prefer='threads')(
        delayed(operation)(param, circuit.copy(deep=True), initial_state) for param in parameters)

    return results


def _check_parallel_configuration(processes, backend):  # pragma: no cover
    """Check if configuration is suitable for efficient parallel execution."""
    import sys
    import psutil
    from qibo.config import raise_error, log

    if sys.platform == "win32" or sys.platform == 'darwin':  # pragma: no cover
        raise_error(
            RuntimeError, "Parallel evaluations supported only on linux.")

    name = backend.name
    if name == "tensorflow":  # pragma: no cover
        raise_error(
            RuntimeError, f"{name} backend does not support parallel evaluations.")

    device = backend.device
    if device is not None and "GPU" in device:  # pragma: no cover
        raise_error(
            RuntimeError, "Parallel evaluations cannot be used with GPU.")

    nthreads = backend.nthreads
    if ((processes is not None and processes * nthreads > psutil.cpu_count()) or
            (processes is None and nthreads != 1)):  # pragma: no cover
        log.warning('Please consider using a lower number of threads per process,'
                    ' or reduce the number of processes for better performance')
