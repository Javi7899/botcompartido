from datetime import date, timedelta

import pytest

from quantbot.data.edgar import InsiderTransaction, parse_form4
from quantbot.data.errors import DataSourceError
from quantbot.db.models import EngineName
from quantbot.engines.insider import InsiderEngine, role_weight

ENGINE = InsiderEngine()
AS_OF = date(2026, 7, 18)

FORM4_XML = """<?xml version="1.0"?>
<ownershipDocument>
    <aff10b5One>0</aff10b5One>
    <issuer>
        <issuerCik>0000320193</issuerCik>
        <issuerTradingSymbol>AAPL</issuerTradingSymbol>
    </issuer>
    <reportingOwner>
        <reportingOwnerRelationship>
            <isDirector>0</isDirector>
            <isOfficer>1</isOfficer>
            <officerTitle>Chief Executive Officer</officerTitle>
            <isTenPercentOwner>0</isTenPercentOwner>
        </reportingOwnerRelationship>
    </reportingOwner>
    <nonDerivativeTable>
        <nonDerivativeTransaction>
            <transactionDate><value>2026-07-10</value></transactionDate>
            <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
            <transactionAmounts>
                <transactionShares><value>10000</value></transactionShares>
                <transactionPricePerShare><value>150.00</value></transactionPricePerShare>
                <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
            </transactionAmounts>
        </nonDerivativeTransaction>
        <nonDerivativeTransaction>
            <transactionDate><value>2026-07-11</value></transactionDate>
            <transactionCoding><transactionCode>M</transactionCode></transactionCoding>
            <transactionAmounts>
                <transactionShares><value>5000</value></transactionShares>
                <transactionPricePerShare><value>50.00</value></transactionPricePerShare>
                <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
            </transactionAmounts>
        </nonDerivativeTransaction>
    </nonDerivativeTable>
</ownershipDocument>
"""


def test_parse_form4() -> None:
    transactions = parse_form4(FORM4_XML)
    assert len(transactions) == 2
    purchase = transactions[0]
    assert purchase.ticker == "AAPL"
    assert purchase.code == "P"
    assert purchase.shares == 10000
    assert purchase.price == 150.0
    assert purchase.acquired is True
    assert purchase.is_officer is True
    assert "Chief Executive" in purchase.officer_title
    assert purchase.rule_10b5_1 is False
    assert transactions[1].code == "M"


def test_parse_form4_malformed_raises() -> None:
    with pytest.raises(DataSourceError, match="no parseable"):
        parse_form4("esto no es xml")
    with pytest.raises(DataSourceError, match="inesperado"):
        parse_form4("<otraCosa/>")


def txn(
    code: str = "P",
    days_ago: int = 5,
    shares: float = 10000,
    price: float | None = 150.0,
    acquired: bool | None = None,
    title: str = "Chief Executive Officer",
    officer: bool = True,
    director: bool = False,
    plan: bool = False,
) -> InsiderTransaction:
    return InsiderTransaction(
        ticker="AAPL",
        transaction_date=AS_OF - timedelta(days=days_ago),
        code=code,
        shares=shares,
        price=price,
        acquired=acquired if acquired is not None else code == "P",
        is_director=director,
        is_officer=officer,
        officer_title=title,
        is_ten_percent_owner=False,
        rule_10b5_1=plan,
    )


def test_ceo_purchase_scores_positive() -> None:
    result = ENGINE.score_ticker("AAPL", [txn()], AS_OF)
    assert result.engine == EngineName.INSIDER
    # $1.5M compra CEO, decay ~0.89 -> tanh(1.335/2) ~ 0.58
    assert result.score > 0.5
    assert "1 compras / 0 ventas" in result.justification


def test_sale_scores_negative_but_weaker() -> None:
    purchase = ENGINE.score_ticker("AAPL", [txn("P")], AS_OF).score
    sale = ENGINE.score_ticker("AAPL", [txn("S")], AS_OF).score
    assert sale < 0
    assert abs(sale) < abs(purchase)  # las ventas pesan 0.25x


def test_rule_10b5_1_excluded() -> None:
    result = ENGINE.score_ticker("AAPL", [txn(plan=True)], AS_OF)
    assert result.score == 0.0
    assert "sin transacciones" in result.justification


def test_option_exercise_excluded() -> None:
    assert ENGINE.score_ticker("AAPL", [txn("M")], AS_OF).score == 0.0


def test_missing_price_excluded() -> None:
    assert ENGINE.score_ticker("AAPL", [txn(price=None)], AS_OF).score == 0.0


def test_old_transaction_excluded() -> None:
    old = txn(days_ago=120)
    assert ENGINE.score_ticker("AAPL", [old], AS_OF).score == 0.0


def test_recency_decay() -> None:
    recent = ENGINE.score_ticker("AAPL", [txn(days_ago=2)], AS_OF).score
    older = ENGINE.score_ticker("AAPL", [txn(days_ago=80)], AS_OF).score
    assert recent > older > 0


def test_role_weights_ordering() -> None:
    ceo = txn()
    vp = txn(title="Vice President, Legal")
    board = txn(title="", officer=False, director=True)
    assert role_weight(ceo) > role_weight(vp) > role_weight(board)


def test_no_transactions_neutral() -> None:
    result = ENGINE.score_ticker("AAPL", [], AS_OF)
    assert result.score == 0.0
