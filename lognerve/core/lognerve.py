import lognerve.core.sdk as sdk
from lognerve.context.context import observe, using_attributes


class _LogNerve:
    initialize = staticmethod(sdk.initialize)
    observe = staticmethod(observe)
    usingAttributes = staticmethod(using_attributes)


lognerve = _LogNerve()
