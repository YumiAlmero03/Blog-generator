from app import create_app


def test_unlimited_rebate_page_uses_supplied_promotion_content():
    app = create_app()
    app.testing = True
    client = app.test_client()

    response = client.get("/unlimited-rebate")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "1.5% Unlimited Rebate" in html
    assert "Daily Slot Rebate" in html
    assert "July 8, 2026 at 12:00 PM" in html
    assert "Previous day’s settled valid bets" in html
    assert "Open to KYC-verified members only." in html
    assert "BYBET General Terms and Conditions apply." in html
