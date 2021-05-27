import numpy as np
from ...tensor.passthrough import is_acceptable_simple_type
from ...tensor.passthrough import PassthroughTensor


class IntermediateGammaTensor(PassthroughTensor):

    def __init__(self, term_tensor, coeff_tensor, symbol_factory, bias_tensor):
        super().__init__(term_tensor)
        self.term_tensor = term_tensor
        self.coeff_tensor = coeff_tensor
        self.bias_tensor = bias_tensor
        self.symbol_factory = symbol_factory

    @property
    def shape(self):
        return self.term_tensor.shape[:-1]

    @property
    def full_shape(self):
        return self.term_tensor.shape

    def sum(self, dim):
        new_term_tensor = np.swapaxes(self.term_tensor, dim, -1).squeeze(dim)
        new_coeff_tensor = np.swapaxes(self.coeff_tensor, dim, -1).squeeze(dim)
        new_bias_tensor = np.sum(dim)

        return IntermediateGammaTensor(term_tensor=new_term_tensor,
                                       coeff_tensor=new_coeff_tensor,
                                       bias_tensor=new_bias_tensor,
                                       symbol_factory=self.symbol_factory)

    def prod(self, dim):
        new_term_tensor = self.term_tensor.prod(dim)
        new_coeff_tensor = self.coeff_tensor.prod(dim)
        new_bias_tensor = self.bias_tensor.prod(dim)
        return IntermediateGammaTensor(term_tensor=new_term_tensor,
                                       coeff_tensor=new_coeff_tensor,
                                       bias_Tensor=new_bias_tensor,
                                       symbol_factory=self.symbol_factory)

    def __add__(self, other):

        if is_acceptable_simple_type(other):

            term_tensor = self.term_tensor
            coeff_tensor = self.coeff_tensor
            bias_tensor = self.bias_tensor + other

        else:

            if self.symbol_factory != other.symbol_factory:
                # TODO: come up with a method for combining symbol factories
                raise Exception("Cannot add two tensors with different symbol encodings")

            # Step 1: Concatenate
            term_tensor = np.concatenate([self.term_tensor, other.term_tensor], axis=-1)
            coeff_tensor = np.concatenate([self.coeff_tensor, other.coeff_tensor], axis=-1)
            bias_tensor = self.bias_tensor + other.bias_tensor

        # TODO: Step 2: Reduce dimensionality if possible (look for duplicates)
        return IntermediateGammaTensor(term_tensor=term_tensor,
                                       coeff_tensor=coeff_tensor,
                                       bias_tensor=bias_tensor,
                                       symbol_factory=self.symbol_factory)

    def __mul__(self, other):

        if is_acceptable_simple_type(other):

            term_tensor = self.term_tensor
            coeff_tensor = self.coeff_tensor * other
            bias_tensor = self.bias_tensor * other

        else:
            if self.symbol_factory != other.symbol_factory:
                # TODO: come up with a method for combining symbol factories
                raise Exception("Cannot add two tensors with different symbol encodings")

            terms = list()
            for self_dim in range(self.term_tensor.shape[-1]):
                for other_dim in range(other.term_tensor.shape[-1]):
                    new_term = np.expand_dims(self.term_tensor[..., self_dim] * other.term_tensor[..., other_dim], -1)
                    terms.append(new_term)

            for self_dim in range(self.term_tensor.shape[-1]):
                new_term = np.expand_dims(self.term_tensor[..., self_dim], -1)
                terms.append(new_term)

            for other_dim in range(self.term_tensor.shape[-1]):
                new_term = np.expand_dims(other.term_tensor[..., self_dim], -1)
                terms.append(new_term)

            term_tensor = np.concatenate(terms, axis=-1)

            coeffs = list()
            for self_dim in range(self.coeff_tensor.shape[-1]):
                for other_dim in range(other.coeff_tensor.shape[-1]):
                    new_coeff = np.expand_dims(self.coeff_tensor[..., self_dim] * other.coeff_tensor[..., other_dim],
                                               -1)
                    coeffs.append(new_coeff)

            for self_dim in range(self.coeff_tensor.shape[-1]):
                new_coeff = np.expand_dims(self.coeff_tensor[..., self_dim] * other.bias_tensor, -1)
                coeffs.append(new_coeff)

            for other_dim in range(self.coeff_tensor.shape[-1]):
                new_coeff = np.expand_dims(other.coeff_tensor[..., self_dim] * self.bias_tensor, -1)
                coeffs.append(new_coeff)

            coeff_tensor = np.concatenate(coeffs, axis=-1)

            bias_tensor = self.bias_tensor * other.bias_tensor

        # TODO: Step 2: Reduce dimensionality if possible (look for duplicates)
        return IntermediateGammaTensor(term_tensor=term_tensor,
                                       coeff_tensor=coeff_tensor,
                                       bias_tensor=bias_tensor,
                                       symbol_factory=self.symbol_factory)
