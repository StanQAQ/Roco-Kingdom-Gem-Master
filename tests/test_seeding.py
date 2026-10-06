from src.seeding import MAX_SEED, generate_random_seed, prompt_for_seed, seed_description, select_seed


def answers(*items: str):
    values = iter(items)
    return lambda _prompt: next(values)


def test_fixed_seed_can_be_selected_by_argument():
    assert select_seed(42, False) == (42, "fixed")
    assert seed_description(42, "fixed") == "固定种子：42"


def test_random_seed_is_a_reusable_32_bit_integer():
    seed = generate_random_seed()
    assert isinstance(seed, int)
    assert 0 <= seed <= MAX_SEED


def test_prompt_supports_fixed_default_and_custom_seed():
    assert prompt_for_seed(answers("f", "")) == (1, "fixed")
    assert prompt_for_seed(answers("fixed", "2026")) == (2026, "fixed")


def test_prompt_supports_random_mode():
    seed, mode = prompt_for_seed(answers("r"))
    assert mode == "random"
    assert 0 <= seed <= MAX_SEED
