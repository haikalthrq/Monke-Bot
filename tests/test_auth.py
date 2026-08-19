import unittest

from monkebot.core.auth import Authorizer


class FakeRole:
    def __init__(self, role_id: int) -> None:
        self.id = role_id


class FakeUser:
    def __init__(self, user_id: int, role_ids: tuple[int, ...] = ()) -> None:
        self.id = user_id
        self.roles = [FakeRole(role_id) for role_id in role_ids]


class FakeInteraction:
    def __init__(self, guild_id: int | None, user: FakeUser) -> None:
        self.guild_id = guild_id
        self.user = user


class AuthorizerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.authorizer = Authorizer(guild_id=1, operator_role_ids=frozenset({30}))

    def test_every_member_can_use_information_commands(self) -> None:
        interaction = FakeInteraction(1, FakeUser(10))
        self.assertTrue(self.authorizer.is_member(interaction))
        self.assertFalse(self.authorizer.can_operate(interaction))

    def test_operator_role_can_run_server_operations(self) -> None:
        interaction = FakeInteraction(1, FakeUser(12, (30,)))
        self.assertTrue(self.authorizer.is_member(interaction))
        self.assertTrue(self.authorizer.can_operate(interaction))

    def test_other_guild_is_always_denied(self) -> None:
        interaction = FakeInteraction(2, FakeUser(10, (30,)))
        self.assertFalse(self.authorizer.is_member(interaction))
        self.assertFalse(self.authorizer.can_operate(interaction))
