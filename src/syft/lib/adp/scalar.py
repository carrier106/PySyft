# stdlib
from collections import defaultdict
from copy import deepcopy
import random
from string import ascii_letters
from typing import Any
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional
from typing import Set
from typing import Tuple
from typing import Union

# third party
from google.protobuf.reflection import GeneratedProtocolMessageType
import numpy as np
from scipy import optimize
from scipy.optimize import OptimizeResult
from sympy import Symbol
from sympy import diff
from sympy import symbols

# syft absolute
from syft.core.common.serde import Serializable

# syft relative
from ...core.common import UID
from ...core.common.serde.serializable import bind_protobuf
from ...proto.lib.adp.scalar_pb2 import Scalar as Scalar_PB
from .adversarial_accountant import publish
from .entity import Entity
from .search import create_lookup_tables_for_symbol
from .search import create_searchable_function_from_polynomial
from .search import flatten_and_maximize_poly
from .search import max_lipschitz_via_jacobian
from .search import minimize_function
from .search import ssid2obj


@bind_protobuf
class Scalar():

    def publish(self, acc, sigma: float = 1.5) -> float:
        return publish([self], acc=acc, sigma=sigma)

    def __str__(self) -> str:
        return "<" + str(type(self).__name__) + ": (" + str(self.min_val) + " < " + str(self.value) + " < " + str(
            self.max_val) + ")>"

    def __repr__(self) -> str:
        return str(self)

    def _object2proto(self) -> Scalar_PB:
        return Scalar_PB(
            id=self.id._object2proto(),
            has_name=True if self.name is not None else False,
            name=self.name if self.name is not None else "",
            has_value=True if self._value is not None else False,
            value=self._value if self._value is not None else 0,
            has_min_val=True if self._min_val is not None else False,
            min_val=self._min_val if self._min_val is not None else 0,
            has_max_val=True if self._max_val is not None else False,
            max_val=self._max_val if self._max_val is not None else 0,
            # has_poly=True if self._poly is not None else False,
            # poly=self._poly if self._poly is not None else None,
            has_entity_name=True if self.entity_name is not None else False,
            entity_name=self.entity_name if self.entity_name is not None else "",
        )

    @staticmethod
    def _proto2object(proto: Scalar_PB) -> "Scalar":
        name: Optional[str] = None
        if proto.has_name:
            name = proto.name

        value: Optional[float] = None
        if proto.has_value:
            value = proto.value

        min_val: Optional[float] = None
        if proto.has_min_val:
            min_val = proto.min_val

        max_val: Optional[float] = None
        if proto.has_max_val:
            max_val = proto.max_val

        entity_name: Optional[str] = None
        if proto.has_entity_name:
            entity_name = proto.entity_name

        return Scalar(
            id=UID._proto2object(proto.id),
            name=name,
            value=value,
            min_val=min_val,
            max_val=max_val,
            entity=entity_name,
        )

    @staticmethod
    def get_protobuf_schema() -> GeneratedProtocolMessageType:
        return Scalar_PB


class IntermediateScalar(Scalar):

    def __init__(self, poly, id=None):
        self.poly = poly
        self._gamma = None
        self.id = id if id else UID()

    def __rmul__(self, other: "Scalar") -> "Scalar":
        return self * other

    def __radd__(self, other: "Scalar") -> "Scalar":
        return self + other

    @property
    def input_scalars(self):
        phi_scalars = list()
        for ssid in self.input_polys:
            phi_scalars.append(ssid2obj[str(ssid)])
        return phi_scalars

    @property
    def input_entities(self):
        return list(set([x.entity for x in self.input_scalars]))

    @property
    def input_polys(self):
        return self.poly.free_symbols

    @property
    def max_val(self):
        return -flatten_and_maximize_poly(-self.poly)[-1].fun

    @property
    def min_val(self):
        return flatten_and_maximize_poly(self.poly)[-1].fun

    @property
    def value(self):
        return self.poly.subs({obj.poly: obj.value for obj in self.input_scalars})


class IntermediatePhiScalar(IntermediateScalar):

    def __init__(self, poly, entity):
        super().__init__(poly=poly)
        self.entity = entity

    def max_lipschitz_wrt_entity(self, *args, **kwargs):
        return self.gamma.max_lipschitz_wrt_entity(*args, **kwargs)

    @property
    def max_lipschitz(self):
        return self.gamma.max_lipschitz

    def __mul__(self, other: "Scalar") -> "Scalar":

        if isinstance(other, IntermediateGammaScalar):
            return self.gamma * other

        if not isinstance(other, IntermediatePhiScalar):
            return IntermediatePhiScalar(poly=self.poly * other, entity=self.entity)

        # if other is referencing the same individual
        if self.entity == other.entity:
            return IntermediatePhiScalar(poly=self.poly * other.poly, entity=self.entity)

        return self.gamma * other.gamma

    def __add__(self, other: "Scalar") -> "Scalar":

        if isinstance(other, IntermediateGammaScalar):
            return self.gamma + other

        # if other is a public value
        if not isinstance(other, Scalar):
            return IntermediatePhiScalar(poly=self.poly + other, entity=self.entity)

        # if other is referencing the same individual
        if self.entity == other.entity:
            return IntermediatePhiScalar(poly=self.poly + other.poly, entity=self.entity)

        return self.gamma + other.gamma

    def __sub__(self, other: "Scalar") -> "Scalar":

        if isinstance(other, IntermediateGammaScalar):
            return self.gamma - other

        # if other is a public value
        if not isinstance(other, IntermediatePhiScalar):
            return IntermediatePhiScalar(poly=self.poly - other, entity=self.entity)

        # if other is referencing the same individual
        if self.entity == other.entity:
            return IntermediatePhiScalar(poly=self.poly - other.poly, entity=self.entity)

        return self.gamma - other.gamma

    @property
    def gamma(self):

        if self._gamma is None:
            self._gamma = GammaScalar(min_val=self.min_val,
                                      value=self.value,
                                      max_val=self.max_val,
                                      entity=self.entity)
        return self._gamma


class OriginScalar(Scalar):
    """A scalar which stores the root polynomial values. When this is a superclass of
    PhiScalar it represents data that was loaded in by a data owner. When this is a superclass
    of GammaScalar this represents the node at which point data from mulitple entities was combined."""

    def __init__(self, min_val, value, max_val, entity=None, id=None):
        self.id = id if id else UID()
        self._value = value
        self._min_val = min_val
        self._max_val = max_val
        self.entity = entity if entity is not None else Entity()

    @property
    def value(self):
        return self._value

    @property
    def max_val(self):
        return self._max_val

    @property
    def min_val(self):
        return self._min_val


class PhiScalar(OriginScalar, IntermediatePhiScalar):
    """A scalar over data from a single entity"""

    def __init__(self, min_val, value, max_val, entity=None, id=None, ssid=None):
        super().__init__(min_val=min_val, value=value, max_val=max_val, entity=entity, id=id)

        # the scalar string identifier (SSID) - because we're using polynomial libraries
        # we need to be able to reference this object in string form. the library doesn't
        # know how to process things that aren't strings
        if ssid is None:
            ssid = str(self.id).split(" ")[1][:-1]  # + "_" + str(self.entity.id).split(" ")[1][:-1]

        self.ssid = ssid

        IntermediatePhiScalar.__init__(self, poly=symbols(self.ssid), entity=self.entity)

        ssid2obj[self.ssid] = self


class IntermediateGammaScalar(IntermediateScalar):
    """"""

    def __add__(self, other):
        if isinstance(other, Scalar):
            if isinstance(other, IntermediatePhiScalar):
                other = other.gamma
            return IntermediateGammaScalar(poly=self.poly + other.poly)
        return IntermediateGammaScalar(poly=self.poly + other)

    def __sub__(self, other):
        if isinstance(other, Scalar):
            if isinstance(other, IntermediatePhiScalar):
                other = other.gamma
            return IntermediateGammaScalar(poly=self.poly - other.poly)
        return IntermediateGammaScalar(poly=self.poly - other)

    def __mul__(self, other):
        if isinstance(other, Scalar):
            if isinstance(other, IntermediatePhiScalar):
                other = other.gamma
            return IntermediateGammaScalar(poly=self.poly * other.poly)
        return IntermediateGammaScalar(poly=self.poly * other)

    def max_lipschitz_via_explicit_search(self, force_all_searches=False):

        r1 = np.array([x.poly for x in self.input_scalars])

        r2_diffs = np.array(
            [GammaScalar(x.min_val, x.value, x.max_val, entity=x.entity).poly for x in self.input_scalars])
        r2 = r1 + r2_diffs

        fr1 = self.poly
        fr2 = self.poly.copy().subs({x[0]: x[1] for x in list(zip(r1, r2))})

        left = np.sum(np.square(fr1 - fr2)) ** 0.5
        right = np.sum(np.square(r1 - r2)) ** 0.5

        C = -left / right

        i2s, s2i = create_lookup_tables_for_symbol(C)
        search_fun = create_searchable_function_from_polynomial(poly=C, symbol2index=s2i)

        r1r2diff_zip = list(zip(r1, r2_diffs))

        s2range = {}
        for _input_scalar, _additive_counterpart in r1r2diff_zip:
            input_scalar = ssid2obj[_input_scalar.name]
            additive_counterpart = ssid2obj[_additive_counterpart.name]

            s2range[input_scalar.ssid] = (input_scalar.min_val, input_scalar.max_val)
            s2range[additive_counterpart.ssid] = (input_scalar.min_val, input_scalar.max_val)

        rranges = list()
        for index, symbol in enumerate(i2s):
            rranges.append(s2range[symbol])

        r2_indices_list = list()
        min_max_list = list()
        for r2_val in r2:
            r2_syms = [ssid2obj[x.name] for x in r2_val.free_symbols]
            r2_indices = [s2i[x.ssid] for x in r2_syms]

            r2_indices_list.append(r2_indices)
            min_max_list.append((r2_syms[0].min_val, r2_syms[0].max_val))

        functions = list()
        for i in range(2):
            f1 = lambda x, i=i: x[r2_indices_list[i][0]] + x[r2_indices_list[i][1]] + min_max_list[i][0]
            f2 = lambda x, i=i: -(x[r2_indices_list[i][0]] + x[r2_indices_list[i][1]]) + min_max_list[i][1]

            functions.append(f1)
            functions.append(f2)

        constraints = [{'type': 'ineq', 'fun': f} for f in functions]

        def non_negative_additive_terms(symbol_vector):
            out = 0
            for index in [s2i[x.name] for x in r2_diffs]:
                out += (symbol_vector[index] ** 2)
            # theres a small bit of rounding error from this constraint - this should
            # only be used as a double check or as a backup!!!
            return out ** 0.5 - 1 / 2 ** 16

        constraints.append({'type': 'ineq', 'fun': non_negative_additive_terms})
        results = minimize_function(f=search_fun, rranges=rranges, constraints=constraints,
                                    force_all_searches=force_all_searches)

        return results, C

    def max_lipschitz_via_jacobian(self, input_entity=None, data_dependent=True, force_all_searches=False,
                                   try_hessian_shortcut=False):
        return max_lipschitz_via_jacobian(scalars=[self], input_entity=input_entity, data_dependent=data_dependent,
                                          force_all_searches=force_all_searches,
                                          try_hessian_shortcut=try_hessian_shortcut)

    @property
    def max_lipschitz(self):
        result = self.max_lipschitz_via_jacobian()[0][-1]
        if isinstance(result, float):
            return -result
        else:
            return -float(result.fun)

    def max_lipschitz_wrt_entity(self, entity):
        result = self.max_lipschitz_via_jacobian(input_entity=entity)[0][-1]
        if isinstance(result, float):
            return -result
        else:
            return -float(result.fun)


class GammaScalar(OriginScalar, IntermediateGammaScalar):
    """A scalar over data from multiple entities"""

    def __init__(self, min_val, value, max_val, entity=None, id=None, ssid=None):
        super().__init__(min_val=min_val, value=value, max_val=max_val, entity=entity, id=id)

        # the scalar string identifier (SSID) - because we're using polynomial libraries
        # we need to be able to reference this object in string form. the library doesn't
        # know how to process things that aren't strings
        if ssid is None:
            ssid = str(self.id).split(" ")[1][:-1] + "_" + str(self.entity.id).split(" ")[1][:-1]

        self.ssid = ssid

        IntermediateGammaScalar.__init__(self, poly=symbols(self.ssid))

        ssid2obj[self.ssid] = self