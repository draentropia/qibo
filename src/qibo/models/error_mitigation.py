# -*- coding: utf-8 -*-
"""Error Mitigation Methods."""
import numpy as np
from qibo import gates
from scipy.optimize import curve_fit

def get_gammas(c, solve=True):
    """Standalone function to compute the ZNE coefficients given the noise levels.
        
    Args:
        c (numpy.ndarray): Array containing the different noise levels, note that in the CNOT insertion paradigm this corresponds to the number of CNOT pairs to be inserted. The canonical ZNE noise levels are obtained as 2*c + 1.
        solve (bool): If ``True`` computes the coeffients by solving the linear system. Otherwise, use the analytical solution valid for the CNOT insertion method.

    Returns:
        numpy.ndarray: The computed coefficients.
    """
    if solve:
        c = 2*c + 1
        a = np.array([ c**i for i in range(len(c)) ])
        b = np.zeros(len(c))
        b[0] = 1
        gammas = np.linalg.solve(a, b)
    else:
        cmax = c[-1]
        gammas = np.array([
            1/(2**(2*cmax)*np.math.factorial(i)) * (-1)**i/(1+2*i) * np.math.factorial(1+2*cmax)/(np.math.factorial(cmax)*np.math.factorial(cmax-i))
            for i in c
        ])
    return gammas

def get_noisy_circuit(circuit, cj):
    """Standalone function to generate the noisy circuit with the CNOT pairs insertion.
        
    Args:
        circuit (qibo.models.circuit.Circuit): Input circuit to modify.
        cj (int): Number of CNOT pairs to add.
    
    Returns:
        qibo.models.circuit.Circuit: The circuit with the inserted CNOT pairs.
    """
    noisy_circuit = circuit.__class__(**circuit.init_kwargs)
    for gate in circuit.queue:
        noisy_circuit.add(gate)
        if gate.__class__ == gates.CNOT:
            control = gate.control_qubits[0]
            target = gate.target_qubits[0]
            for i in range(cj):
                noisy_circuit.add(gates.CNOT(control, target))
                noisy_circuit.add(gates.CNOT(control, target))
    return noisy_circuit

def ZNE(circuit, observable, c, init_state=None, CNOT_noise_model=None):
    """Runs the Zero Noise Extrapolation method for error mitigation.
    The different noise levels are realized by the insertion of pairs of CNOT gates that resolve to the identiy in the noise-free case.

    Args:
        circuit (qibo.models.circuit.Circuit): Input circuit.
        observable (numpy.ndarray): Observable to measure.
        c (numpy.ndarray): Sequence of noise levels.
        init_state (numpy.ndarray): Initial state. 
        CNOT_noise_model (qibo.noise.NoiseModel): Noise model applied to each CNOT gate, used for simulating noisy CNOTs.

    Returns:
        numpy.ndarray: Estimate of the expected value of ``observable`` in the noise free condition.
    """
    assert circuit.density_matrix, "Circuit.density_matrix == True is needed."
    expected_val = []
    for cj in c:
        noisy_circuit = get_noisy_circuit(circuit, cj)
        if CNOT_noise_model != None:
            noisy_circuit = CNOT_noise_model.apply(noisy_circuit)
        rho = noisy_circuit(initial_state = init_state)
        expected_val.append(observable.dot(rho.state()).trace())
    gamma = get_gammas(c, solve=False)
    return (gamma*expected_val).sum()

def sample_training_circuit(circuit, replacement_gates=[(gates.RZ, {'theta': n*np.pi/2}) for n in range(4)], sigma=0.5):
    """Samples a training circuit for CDR by susbtituting some of the non-Clifford gates.

    Args:
        circuit (qibo.models.circuit.Circuit): Circuit to sample from, decomposed in `RX(pi/2)`, `X`, `CNOT` and `RZ` gates.
        replacement_gates (list): Candidates for the substitution of the non-Clifford gates. The list should be composed by tuples of the form (gates.XYZ, kwargs). For example, phase gates are used by default: `list((RZ, {'th':0}), (RZ, {'th':pi/2}), (RZ, {'th':pi}), (RZ, {'th':3*pi/2}))`.
        sigma (float): Scaling factor for the Frobenius norm.
    
    Returns:
        qibo.models.circuit.Circuit: The sampled circuit.
    """
    # Find all the non-Clifford RZ gates
    gates_to_replace = []
    for i, gate in enumerate(circuit.queue):
        if gate.__class__ == gates.RZ:
            if gate.init_kwargs['theta'] % (np.pi/2) != 0.:
                gates_to_replace.append((i, gate))                
                
    # For each RZ gate build the possible candidates and
    # compute the frobenius distance to the candidates
    replacement, distance = [], []
    for _, gate in gates_to_replace:
        rep_gates = np.array([
            rg(*gate.init_args, **kwargs)
            for rg, kwargs in replacement_gates
        ])

        replacement.append(rep_gates)
        distance.append(
            np.linalg.norm(
                gate.matrix - [rep_gate.matrix for rep_gate in rep_gates] ,
                ord='fro',
                axis=(1,2)
            )
        )
    distance = np.vstack(distance)
    # Compute the scores
    prob = np.exp(-distance**2/sigma**2)
    # Sample which of the RZ found to substitute
    index = np.random.choice(
        range(len(gates_to_replace)),
        size=min(int(len(gates_to_replace)/2),50),
        replace=False,
        p=prob.sum(-1)/prob.sum()
    )
    gates_to_replace = np.array([gates_to_replace[i] for i in index])
    prob = [(i,prob[i]) for i in index]
    # Sample which replacement gate to substitute with
    replacement = [
        replacement[p[0]][np.random.choice(range(len(p[1])), size=1, p=p[1]/p[1].sum())[0]]
        for p in prob 
    ]
    # Build the training circuit by substituting the sampled gates
    sampled_circuit = circuit.__class__(**circuit.init_kwargs)
    for i, gate in enumerate(circuit.queue):
        if len(gates_to_replace)!=0 and i in gates_to_replace[:,0]:
            #sampled_circuit.add(replacement.pop(gates_to_replace[:,0]))
            index=np.where(gates_to_replace[:,0]==i)[0][0]
            sampled_circuit.add(replacement.pop(index))
            #gates_to_replace=gates_to_replace[1:]
            gates_to_replace=np.delete(gates_to_replace,index,axis=0)
        else:
            sampled_circuit.add(gate)
    return sampled_circuit

def CDR(circuit, observable, noise_model, model=lambda x,a,b: a*x + b, n_training_samples=100, init_state=None):
    """Runs the CDR error mitigation method.
    
    Args:
        circuit (qibo.models.circuit.Circuit): Input circuit decomposed in the primitive gates: X, CNOT, RX(pi/2), RZ(theta).
        observable (numpy.ndarray): Observable to measure.
        noise_model (qibo.noise.NoiseModel): Noise model used for simulating noisy computation.
        model : Model used for fitting. This should be a callable function object `f(x, *params)` taking as input the predictor variable and the parameters. By default a simple linear model `f(x,a,b) := a*x + b` is used.
        n_training_samples (int): Number of training circuits to sample.
        init_state (numpy.ndarray): Initial state. 

    Returns:
        float: Returns the estimated expected value of `observable`.
    """
    # Sample the training set
    training_circuits = [sample_training_circuit(circuit) for n in range(n_training_samples)]
    # Run the sampled circuits
    expected_val = {'noise-free': [], 'noisy': []}
    for c in training_circuits:
        rho = c(initial_state = init_state)
        val = observable.dot(rho.state()).trace()
        expected_val['noise-free'].append(val)
        rho = noise_model.apply(c)(initial_state = init_state)
        val = observable.dot(rho.state()).trace()
        expected_val['noisy'].append(val)                                                
    # Fit the model
    optimal_params = curve_fit(model, expected_val['noisy'], expected_val['noise-free'])
    # Run the input circuit
    rho = noise_model.apply(circuit)(initial_state = init_state)
    val = observable.dot(rho.state()).trace()
    return [model(val, *optimal_params[0]), val, optimal_params[0], expected_val]
    
def vnCDR(circuit, observable, noise_levels, noise_model, model=lambda x,a: a*x, n_training_samples=100, init_state=None):
    """Runs the vnCDR error mitigation method.
    
    Args:
        circuit (qibo.models.circuit.Circuit): Input circuit decomposed in the primitive gates: X, CNOT, RX(pi/2), RZ(theta).
        observable (numpy.ndarray): Observable to measure.
        noise_levels (numpy.ndarray): Sequence of noise levels.
        noise_model (qibo.noise.NoiseModel): Noise model used for simulating noisy computation.
        model : Model used for fitting. This should be a callable function object `f(x, *params)` taking as input the predictor variable and the parameters. By default a simple linear model `f(x,a) := a*x` is used.
        n_training_samples (int): Number of training circuits to sample.
        init_state (numpy.ndarray): Initial state. 

    Returns:
        float: Returns the estimated expected value of `observable`.
    """
    # Sample the training circuits
    training_circuits = [sample_training_circuit(circuit) for n in range(n_training_samples)]
    expected_val = {'noise-free': [], 'noisy': []}
    # Add the different noise levels and run the circuits
    for c in training_circuits:
        rho = c(initial_state = init_state)
        val = observable.dot(rho.state()).trace()
        expected_val['noise-free'].append(val)
        for level in noise_levels:
            noisy_c = get_noisy_circuit(c, level)
            rho = noise_model.apply(noisy_c)(initial_state = init_state)
            val = observable.dot(rho.state()).trace()
            expected_val['noisy'].append(val)
    # Repeat noise-free values for each noise level
    expected_val['noisy'] = np.array(expected_val['noisy'])
    expected_val['noise-free'] = np.vstack([ expected_val['noise-free'] for i in range(len(noise_levels)) ]).T.flatten()
    # Fit the model
    optimal_params = curve_fit(model, expected_val['noisy'], expected_val['noise-free'])
    # Run the input circuit
    rho = circuit(initial_state = init_state)
    val = observable.dot(rho.state()).trace()
    return model(val, *optimal_params)
