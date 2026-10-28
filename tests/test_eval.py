from dledger import evalkit


def test_graph_guided_beats_random_at_equal_cost():
    res = evalkit.run(n=150, seed=7)
    full, guided, rnd = res["full_sweep"], res["graph_guided"], res["random_budget"]
    assert full["stale_recall"] == 1.0 and full["stale_precision"] == 1.0
    assert guided["verifications"] < full["verifications"]
    assert guided["verifications"] == rnd["verifications"]
    assert guided["stale_recall"] > rnd["stale_recall"]
    assert guided["dependent_recall"] > rnd["dependent_recall"]
    assert guided["stale_precision"] == 1.0
