"""Regression: LLM text with non-cp1252 chars must not crash the console (GAPS F5)."""
import builtins

from syngen.pipeline import ConsoleIO


def test_safe_print_survives_unencodable_unicode(monkeypatch, capsys):
    """Simulate a cp1252 console: print() raises for characters like approx sign."""
    real_print = builtins.print
    calls = []

    def cp1252_print(*args, **kwargs):
        text = " ".join(str(a) for a in args)
        try:
            text.encode("cp1252")
        except UnicodeEncodeError:
            raise UnicodeEncodeError("cp1252", text, 0, 1,
                                     "character maps to <undefined>")
        calls.append(text)
        real_print(text)

    monkeypatch.setattr(builtins, "print", cp1252_print)
    io = ConsoleIO()
    io.inform("APAC avg ~17.5pp — premium holds")  # ~ and em dash break cp1252
    assert len(calls) == 1
    out = capsys.readouterr().out
    assert "?" in out or "~" in out  # replacement happened, no exception


def test_safe_print_normal_text_untouched(capsys):
    ConsoleIO._safe_print("plain ascii output")
    assert capsys.readouterr().out.strip() == "plain ascii output"
