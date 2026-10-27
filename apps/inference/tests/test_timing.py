from inference.timing import collect, stage


def test_stages_are_summed_inside_collect() -> None:
    with collect() as timings:
        with stage("a"):
            pass
        with stage("a"):
            pass
        with stage("b"):
            pass
    assert set(timings) == {"a", "b"}
    assert all(value >= 0 for value in timings.values())


def test_stage_outside_collect_records_nothing() -> None:
    with stage("a"):
        pass
    with collect() as timings:
        pass
    assert timings == {}


def test_failing_stage_is_still_timed() -> None:
    with collect() as timings:
        try:
            with stage("boom"):
                raise ValueError
        except ValueError:
            pass
    assert "boom" in timings
