def _call_with_accepted_kwargs(fn: Callable[..., Any], **kwargs):
    """
    Backward-compat call helper:

    1) Prefer signature-based filtering when possible.
    2) If signature introspection fails OR the function still raises
       "unexpected keyword argument", iteratively drop the offending kw
       and retry a few times.

    This keeps old/new API surfaces compatible without hiding real errors.
    """
    filtered = dict(kwargs)
    try:
        sig = inspect.signature(fn)
        filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
        return fn(**filtered)
    except TypeError as e:
        msg = str(e)
        m = _UNEXPECTED_KW_RE.search(msg)
        if not m:
            raise
        filtered = dict(kwargs)
    except Exception:
        filtered = dict(kwargs)

    max_retries = 12
    last_err: Optional[Exception] = None
    for _ in range(max_retries):
        try:
            return fn(**filtered)
        except TypeError as e:
            msg = str(e)
            m = _UNEXPECTED_KW_RE.search(msg)
            if not m:
                raise
            bad_kw = m.group(1)
            if bad_kw not in filtered:
                raise
            filtered.pop(bad_kw, None)
            last_err = e

    if last_err:
        raise last_err
    return fn(**filtered)


def _require_import(name: str, import_attempts: list[Callable[[], Any]]) -> Any:
    """
    Try a list of import attempt callables. If none work, stop with a clear error.
    """
    last: Optional[Exception] = None
    for attempt in import_attempts:
        try:
            v = attempt()
            if v is not None:
                return v
        except Exception as e:
            last = e

    st.error(f"Import error: required dependency '{name}' could not be imported.")
    if last:
        st.code(str(last))
    st.stop()


