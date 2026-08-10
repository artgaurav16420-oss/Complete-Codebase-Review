import unittest
from unittest.mock import patch

from api.orders import get_orders

class TestOrders(unittest.TestCase):
    @patch('api.orders._fetch_items')
    @patch('api.orders._fetch_orders')
    def test_get_orders_success(self, mock_fetch_orders, mock_fetch_items):
        mock_fetch_orders.return_value = [{"id": 1, "date": "2024-01-01"}]
        mock_fetch_items.return_value = [{"name": "Widget", "price": 9.99}, {"name": "Gadget", "price": 24.99}]

        results = get_orders(123)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["order"]["id"], 1)
        self.assertEqual(len(results[0]["items"]), 2)
        self.assertAlmostEqual(results[0]["total"], 34.98)

        mock_fetch_orders.assert_called_once_with(123)
        mock_fetch_items.assert_called_once_with(1)

    @patch('api.orders._fetch_items')
    @patch('api.orders._fetch_orders')
    def test_get_orders_no_orders(self, mock_fetch_orders, mock_fetch_items):
        mock_fetch_orders.return_value = []

        results = get_orders(123)

        self.assertEqual(results, [])
        mock_fetch_orders.assert_called_once_with(123)
        mock_fetch_items.assert_not_called()

    @patch('api.orders._fetch_items')
    @patch('api.orders._fetch_orders')
    def test_get_orders_no_items(self, mock_fetch_orders, mock_fetch_items):
        mock_fetch_orders.return_value = [{"id": 1, "date": "2024-01-01"}]
        mock_fetch_items.return_value = []

        results = get_orders(123)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["total"], 0)
        mock_fetch_orders.assert_called_once_with(123)
        mock_fetch_items.assert_called_once_with(1)
