from warnings import warn
from msgpackutil.base import Hook, HOOKS

__author__ = 'basca'

_LABEL = 'l'
_ID = 'i'
_SEL = 's'
_DTYPE = 'd'
_LANG = 'a'
_TYPE = 't'


class RdfLiteralHook(Hook):
    def reduce(self, rdf_literal):
        return {
            _LABEL: rdf_literal.__label,
            _DTYPE: rdf_literal.__dtype,
            _LANG: rdf_literal.__lang,
            _TYPE: rdf_literal.__type,
        }


    def create(self, rdf_literal_dict):
        rdflit = RdfLiteral(rdf_literal_dict[_LABEL])
        rdflit.__dtype = rdf_literal_dict[_DTYPE]
        rdflit.__lang = rdf_literal_dict[_LANG]
        rdflit.__type = rdf_literal_dict[_TYPE]
        return rdflit


class QueryVarHook(Hook):
    def reduce(self, query_var):
        return {
            _LABEL: query_var.__label,
            _ID: query_var.id,
            _SEL: query_var.selectivity,
        }


    def create(self, query_var_dict):
        query_var = QueryVar(query_var_dict[_LABEL])
        query_var.id = query_var_dict[_ID]
        query_var.selectivity = query_var_dict[_SEL]
        return query_var


try:
    from cytokyotygr import RdfLiteral, QueryVar

    HOOKS.register(2, RdfLiteralHook)
    HOOKS.register(3, QueryVarHook)
except ImportError:
    warn("could not find cytokyotygr, RdfLiteral & QueryVar not registered.")