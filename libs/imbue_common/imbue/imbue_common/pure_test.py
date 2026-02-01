from imbue.imbue_common.pure import pure


def test_pure_decorator_returns_same_function() -> None:
    @pure
    def add(a: int, b: int) -> int:
        return a + b

    assert add(1, 2) == 3


def test_pure_decorator_preserves_function_name() -> None:
    @pure
    def my_function() -> str:
        return "hello"

    assert my_function.__name__ == "my_function"
