from pipeline.salts import strip_to_parent


def test_strip_to_parent_single_component_unchanged():
    assert strip_to_parent("CCO") == "CCO"


def test_strip_to_parent_picks_largest_fragment():
    # sodium acetate: acetate ion is the larger/parent fragment
    assert strip_to_parent("CC(=O)[O-].[Na+]") == "CC(=O)[O-]"


def test_strip_to_parent_three_fragments():
    assert strip_to_parent("[Cl-].[Cl-].CC(C)(C)N") == "CC(C)(C)N"
