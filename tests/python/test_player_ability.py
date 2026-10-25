import unittest;
from unittest.mock import patch;

from dqd_scroll.api.dqd_api import fetch_player_ability;
from dqd_scroll.api.config import DQD_ABILITY_REFERER, DQD_SPORT_HEADERS;
from dqd_scroll.lib.player_ability import parse_player_ability;
from dqd_scroll.shared import load_position_map;


class PlayerAbilityTest(unittest.TestCase):
    def test_only_flagged_position_values_compete_and_average_is_ignored(self):
        response = {
            'errno': 0,
            'data': {
                'average': {'val': 91},
                'good_pos': {'val': 'LW'},
                'fields': [
                    {'name': '前腰', 'val': 99, 'lv': 'lv1'},
                    {'name': '左边锋', 'val': 92, 'lv': 'lv1_f'},
                    {'name': '中锋', 'val': 93, 'lv': 'lv1_f'},
                ],
            },
        };
        result = parse_player_ability(response, 50259656, load_position_map());
        self.assertEqual((result.person_id, result.ability, result.position), (50259656, 93, 'ST'));

    def test_equal_values_keep_first_position_as_reference_function(self):
        response = {'errno': 0, 'data': {'fields': [
            {'name': '左边锋', 'val': '93', 'lv': 'lv1_f'},
            {'name': '中锋', 'val': 93, 'lv': 'lv1_f'},
        ]}};
        self.assertEqual(parse_player_ability(response, 1, load_position_map()).position, 'LW');

    def test_goalkeeper_uses_shared_mapping(self):
        response = {'errno': 0, 'data': {'fields': [{'name': '守门员', 'val': 90, 'lv': 'lv1_f'}]}};
        self.assertEqual(parse_player_ability(response, 1, load_position_map()).position, 'GK');

    def test_empty_or_unflagged_fields_do_not_use_another_value(self):
        for fields in ([], [{'name': '中锋', 'val': 93, 'lv': 'lv1'}]):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                parse_player_ability({'errno': 0, 'data': {'average': {'val': 91}, 'fields': fields}}, 1, load_position_map());

    def test_unknown_position_invalid_value_and_business_failure_are_rejected(self):
        for field in (
            {'name': '未配置位置', 'val': 93, 'lv': 'lv1_f'},
            {'name': '中锋', 'val': True, 'lv': 'lv1_f'},
            {'name': '中锋', 'val': '-', 'lv': 'lv1_f'},
            {'name': '中锋', 'val': -1, 'lv': 'lv1_f'},
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                parse_player_ability({'errno': 0, 'data': {'fields': [field]}}, 1, load_position_map());
        with self.assertRaises(ValueError):
            parse_player_ability({'errno': 1, 'errmsg': 'not found'}, 1, load_position_map());

    def test_request_preserves_person_id_and_empty_player_type_parameter(self):
        with patch('dqd_scroll.api.dqd_api.get_json', return_value={}) as get_json:
            fetch_player_ability(50259656);
        get_json.assert_called_once_with(
            'https://sport-data.dongqiudi.com/soccer/data/sofifa/v1/player_ability/50259656?player_type=', 30,
            {**DQD_SPORT_HEADERS, 'Referer': DQD_ABILITY_REFERER},
        );


if __name__ == '__main__':
    unittest.main();
