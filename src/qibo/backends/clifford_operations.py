from functools import cache


class CliffordOperations:
    """Operations performed by clifford gates on the stabilizers state tableau representation"""

    def __init__(self):
        import numpy as np

        self.np = np

    def H(self, tableau, q, nqubits):
        new_tab = tableau.copy()
        self.set_r(
            new_tab,
            self.get_r(new_tab, nqubits)
            ^ (
                self.get_x(new_tab, nqubits)[:, q] * self.get_z(new_tab, nqubits)[:, q]
            ).flatten(),
        )
        new_tab[:, [q, nqubits + q]] = new_tab[:, [nqubits + q, q]]
        return new_tab

    def CNOT(self, tableau, control_q, target_q, nqubits):
        new_tab = tableau.copy()
        x, z = self.get_x(new_tab, nqubits), self.get_z(new_tab, nqubits)
        self.set_r(
            new_tab,
            self.get_r(tableau, nqubits)
            ^ (x[:, control_q] * z[:, target_q]).flatten()
            * (x[:, target_q] ^ z[:, control_q] ^ 1).flatten(),
        )

        new_tab[:-1, target_q] = x[:, target_q] ^ x[:, control_q]
        new_tab[:-1, nqubits + control_q] = z[:, control_q] ^ z[:, target_q]
        return new_tab

    def S(self, tableau, q, nqubits):
        new_tab = tableau.copy()
        self.set_r(
            new_tab,
            self.get_r(tableau, nqubits)
            ^ (
                self.get_x(tableau, nqubits)[:, q] * self.get_z(tableau, nqubits)[:, q]
            ).flatten(),
        )
        new_tab[:-1, nqubits + q] = (
            self.get_z(tableau, nqubits)[:, q] ^ self.get_x(tableau, nqubits)[:, q]
        )
        return new_tab

    # valid for a standard basis measurement only
    def M(self, state, qubits, nqubits, collapse=False):
        sample = []
        state_copy = state if collapse else state.copy()
        for q in qubits:
            x = CliffordOperations.get_x(state_copy, nqubits)
            p = x[nqubits:, q].nonzero()[0] + nqubits
            # random outcome, affects the state
            if len(p) > 0:
                p = p[0].item()
                for i in x[:, q].nonzero()[0]:
                    if i != p:
                        state_copy = self.rowsum(state_copy, i.item(), p, nqubits)
                state_copy[p - nqubits, :] = state_copy[p, :]
                outcome = int(self.np.random.randint(2, size=1))
                state_copy[p, :] = 0
                state_copy[p, -1] = outcome
                state_copy[p, nqubits + q] = 1
                sample.append(outcome)
                # determined outcome, state unchanged
            else:
                CliffordOperations.set_scratch(state_copy, 0)
                for i in (x[:, q] == 1).nonzero()[0]:
                    state_copy = self.rowsum(
                        state_copy,
                        2 * nqubits,
                        i.item() + nqubits,
                        nqubits,
                        include_scratch=True,
                    )
                sample.append(int(CliffordOperations.get_scratch(state_copy)[-1]))
        return sample

    @staticmethod
    def get_r(tableau, nqubits, include_scratch=False):
        return tableau[
            : -1 + (2 * nqubits + 2) * int(include_scratch),
            -1,
        ]

    @staticmethod
    def set_r(tableau, val):
        tableau[:-1, -1] = val

    @staticmethod
    def get_x(tableau, nqubits, include_scratch=False):
        return tableau[: -1 + (2 * nqubits + 2) * int(include_scratch), :nqubits]

    @staticmethod
    def set_x(tableau, nqubits, val):
        tableau[:-1, nqubits] = val

    @staticmethod
    def get_z(tableau, nqubits, include_scratch=False):
        return tableau[: -1 + (2 * nqubits + 2) * int(include_scratch), nqubits:-1]

    @staticmethod
    def set_z(tableau, nqubits, val):
        tableau[:-1, nqubits:-1] = val

    @staticmethod
    def get_scratch(tableau):
        return tableau[-1, :]

    @staticmethod
    def set_scratch(tableau, val):
        tableau[-1, :] = val

    @cache
    @staticmethod
    def nqubits(shape):
        return int((shape - 1) / 2)

    @cache
    @staticmethod
    def exponent(x1, z1, x2, z2):
        if x1 == z1:
            if x1 == 0:
                return 0
            elif x1 == 1:
                return z2 - x2
        else:
            if x1 == 1:
                return z2 * (2 * x2 - 1)
            elif x1 == 0:
                return x2 * (1 - 2 * z2)

    def rowsum(self, tableau, h, i, nqubits, include_scratch=False):
        exponents = []
        new_tab = tableau.copy()
        x, z = self.get_x(new_tab, nqubits, include_scratch), self.get_z(
            new_tab, nqubits, include_scratch
        )
        for j in range(nqubits):
            x1, x2 = x[[i, h], [j, j]]
            z1, z2 = z[[i, h], [j, j]]
            exponents.append(CliffordOperations.exponent(x1, z1, x2, z2))
        if (2 * new_tab[h, -1] + 2 * new_tab[i, -1] + self.np.sum(exponents)) % 4 == 0:
            new_tab[h, -1] = 0
        else:  # could be good to check that the expression above is == 2 here...
            new_tab[h, -1] = 1
        new_tab[h, :nqubits] = x[i, :] ^ x[h, :]
        new_tab[h, nqubits:-1] = z[i, :] ^ z[h, :]
        return new_tab


from qibo import gates


def tableau_to_generators(tableau, return_array=False):
    import numpy as np

    bits_to_gate = {"00": gates.I, "01": gates.X, "10": gates.Z, "11": gates.Y}

    nqubits = int((tableau.shape[0] - 1) / 2)
    phases = 1j ** (1 * tableau[nqubits:-1, -1])
    tmp = 1 * tableau[nqubits:-1, :-1]
    X, Z = tmp[:, :nqubits], tmp[:, nqubits:]
    generators = []
    for x, z in zip(X, Z):
        paulis = []
        for i, (xx, zz) in enumerate(zip(x, z)):
            paulis.append(bits_to_gate[f"{zz}{xx}"](i))
        if return_array:
            matrix = paulis[0].matrix()
            for p in paulis[1:]:
                matrix = np.tensordot(matrix, p.matrix(), axes=0)
            generators.append(matrix.reshape(2**nqubits, 2**nqubits))
        else:
            generators.append(paulis)
    return generators, phases
