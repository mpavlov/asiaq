"""Contains patcher function"""

from functools import wraps
from mock import patch as Patch


def patcher(patches, decorators=None, **kwargs):
    """
    A generic patcher which takes a list of patches and returns a patch decorator.

    Use it to define your own patch decorators.

        >>> from mock import patch, Mock
        >>> from moto import mock_ec2
        >>> your_patch_decorator = patcher([patch("module1.foo", kwargs_field="kwargs_field1"),
        ...                                 patch("module2.bar", kwargs_field="kwargs_field2")],
        ...                                decorators=[mock_ec2],
        ...                                additional_mock1=Mock(),
        ...                                additional_mock2=Mock())

    If you want to pass the mock your patch creates to the wrapped function's kwargs, set the
    kwargs_field argument in your patch call.  Note that patches are applied in list order, and
    decorators are applied _after_ the patches, also in list order.  Supply additional mocks as
    keyword arguments, your mocks are passed to the wrapped function in the same arguments.
    """
    additional_fields = kwargs

    def _patch_decorator(func):
        @wraps(func)
        def _patched(*args, **kwargs):
            try:
                for patch in patches:
                    mock = patch.start()
                    if isinstance(mock.kwargs_field, str):
                        kwargs[mock.kwargs_field] = mock

                # Merge additional fields into kwargs with kwargs taking precedence
                kwargs = dict(additional_fields.items() + kwargs.items())

                retval = func(*args, **kwargs)
            finally:
                Patch.stopall()

            return retval

        for decorator in decorators:
            _patched = decorator(_patched)

        return _patched

    return _patch_decorator
