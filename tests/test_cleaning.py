from retail_analytics import cleaning


def test_sheet_overlap_and_duplicates_removed(raw_sample):
    clean, log = cleaning.clean(raw_sample)
    audit = log.to_frame().set_index("step")
    assert audit.loc["Remove sheet overlap", "rows"] == 1
    assert audit.loc["Drop exact duplicates", "rows"] == 1
    assert len(clean) == len(raw_sample) - 2


def test_every_line_gets_exactly_one_known_type(raw_sample):
    clean, _ = cleaning.clean(raw_sample)
    assert clean["line_type"].notna().all()
    assert set(clean["line_type"]) <= set(cleaning.LINE_TYPES)
    by_invoice = dict(zip(clean["invoice"], clean["line_type"]))
    assert by_invoice["C536401"] == "cancellation"
    assert by_invoice["536402"] == "non_product"
    assert by_invoice["536403"] == "stock_adjustment"
    assert by_invoice["536404"] == "zero_price"
    assert by_invoice["A536405"] == "bad_debt_adjustment"
    assert by_invoice["536365"] == "sale"


def test_cancellation_is_matched_to_its_sale(raw_sample):
    clean, _ = cleaning.clean(raw_sample)
    sale = clean[clean["invoice"] == "536400"].iloc[0]
    canc = clean[clean["invoice"] == "C536401"].iloc[0]
    assert sale["was_cancelled"] and canc["matched_cancellation"]
    # a sale nobody cancelled stays unflagged
    assert not clean.loc[clean["invoice"] == "536366", "was_cancelled"].any()


def test_net_revenue_nets_out_cancellations(raw_sample):
    clean, _ = cleaning.clean(raw_sample)
    lines = clean[clean["line_type"].isin(["sale", "cancellation"])]
    net = lines.loc[lines["stock_code"] == "21730", "revenue"].sum()
    assert net == 0


def test_guests_are_flagged_not_dropped(raw_sample):
    clean, _ = cleaning.clean(raw_sample)
    guest_sales = clean[(clean["line_type"] == "sale") & clean["is_guest"]]
    assert list(guest_sales["invoice"]) == ["536406"]
