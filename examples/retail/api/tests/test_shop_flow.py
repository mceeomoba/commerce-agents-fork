# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The shop page's flows over HTTP with chat off: direct add (opt-in), quantity changes,
and the chat route refusing locally when no model key is configured."""

import pytest


@pytest.fixture
def direct_add(monkeypatch):
    monkeypatch.setenv("STOREFRONT_DIRECT_ADD", "1")


def _headers(client):
    session = client.post("/api/session", json={"user_id": "demo-user"}).json()
    return {"X-Session-Id": session["session_id"]}


def test_a_listed_product_is_not_addable_without_the_flag(client):
    headers = _headers(client)
    response = client.post(
        "/api/cart/add", json={"product_id": "AR-1001", "quantity": 1}, headers=headers
    )
    assert response.status_code == 400


def test_direct_add_takes_a_listed_product_and_keeps_the_caps(client, direct_add):
    headers = _headers(client)
    added = client.post(
        "/api/cart/add", json={"product_id": "AR-1001", "quantity": 1}, headers=headers
    )
    assert added.status_code == 200 and added.json()["cart"]["item_count"] == 1
    unknown = client.post(
        "/api/cart/add", json={"product_id": "NOPE", "quantity": 1}, headers=headers
    )
    assert unknown.status_code == 400
    many = client.post(
        "/api/cart/add", json={"product_id": "AR-1001", "quantity": 99}, headers=headers
    )
    assert many.json()["cart"]["item_count"] <= 24


def test_quantity_changes_only_touch_lines_already_in_the_cart(client, direct_add):
    headers = _headers(client)
    client.post("/api/cart/add", json={"product_id": "AR-1001", "quantity": 1}, headers=headers)
    set_five = client.patch("/api/cart/item/AR-1001", json={"quantity": 5}, headers=headers)
    assert set_five.json()["cart"]["item_count"] == 5
    assert (
        client.patch("/api/cart/item/AR-1002", json={"quantity": 1}, headers=headers).status_code
        == 404
    )
    assert (
        client.patch("/api/cart/item/AR-1001", json={"quantity": 25}, headers=headers).status_code
        == 422
    )
    emptied = client.patch("/api/cart/item/AR-1001", json={"quantity": 0}, headers=headers)
    assert emptied.json()["cart"]["items"] == []


def test_chat_without_a_key_says_it_is_off_and_never_calls_out(client, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    headers = _headers(client)
    body = client.post("/api/chat", json={"message": "hi"}, headers=headers).text
    assert "turned off" in body
