# Executive Summary — Retail Customer & Revenue Analytics

**Business:** UK online giftware retailer selling mostly to small wholesalers · **Period:** Dec-2009 – Dec-2011
**Data:** 1.07M raw transaction lines → 1.00M clean sale lines, 39.5k orders, 5.9k customers, 4.9k products, 43 countries

## The headline

Revenue looks healthy: net revenue grew **+1.9%** to **£9.33M** in trading year 2011 (Dec–Nov).
Underneath, the business is **running on its existing customers**:

- **Acquisition has stalled.** Sales from first-time customers fell **54%** year on year
  (Jan–Nov: £1.51M → £0.70M) and first-time customers fell from 3,288 to 1,509. Part of the
  2010 figure is inflated by the data starting in Dec-2009, but the direction is unambiguous.
- **Existing customers are ordering less often.** Orders per customer fell from 4.29 to 4.11,
  a **−£366k** drag. Higher order values (+£155k), slightly more customers (+£105k) and guest
  checkouts (+£342k) more than covered it — this year.
- **New customers are sticking less.** Six months after their first order, 17% of 2011's
  H1 cohorts were still ordering vs 22% for 2010's.

## What the data says about customers

| Finding | Number |
|---|---|
| Revenue concentration | Top 20% of customers = **77%** of revenue; top 1% = **31%** |
| Champions (RFM) | **27%** of customers, **72%** of revenue, last order a median 18 days ago |
| At Risk + Can't Lose Them | 966 customers, **£1.67M** lifetime revenue, **£399k** predicted next-12-month revenue |
| Typical gap between orders | median **32 days**; 75% of repeat orders within **70 days** |
| Predicted next-12-month revenue | **£8.72M** (BG/NBD + Gamma-Gamma CLV model) |

The CLV model was validated out-of-sample: fitted on Dec-2009–Jun-2011, it predicted
7,605 purchases in the following 26 weeks against 7,721 actual (**−1.5%**), with 38% lower
per-customer error than a run-rate baseline.

## What the data says about products and operations

- **Customers buy collections, not items.** 88% of the 50 strongest product associations are
  sibling designs (e.g. the three *Poppy's Playhouse* rooms: 79–84% of buyers of one buy
  another; lift 42–46×).
- **Revenue is concentrated in a narrow range:** the top 20% of SKUs drive 78% of revenue.
- **Q4 dominates:** November alone is **1.8×** an average month. A weekly forecast backtested at
  **13.7% error** (12% better than "same week last year") is ready for stock and staffing plans.
- **Cancellations are creeping up:** 2.6% → 3.1% of gross sales; Spain runs at 13%.
- **13% of sales have no customer ID**, so they are invisible to CRM.

## Recommendations

| # | Action | Why | How to measure |
|---|---|---|---|
| 1 | **Make new-customer acquisition a tracked KPI** and investigate what changed in 2011 (channels, spend, catalogue) | First-time sales halved; the base is ageing | Monthly new customers and their M1/M3 retention |
| 2 | **Second-order programme** — triggered email at day 30, offer at day 60 | Only ~21% of new customers return in month 1; median re-order gap is 32 days | M1 retention of treated vs control cohorts (A/B test) |
| 3 | **Account-manager outreach to the 110 "Can't Lose Them" customers** | £6.2k average lifetime spend each; repeat buyers' median P(alive) is just 38% | Reactivation rate within 90 days |
| 4 | **"Complete the collection" recommendations and bundle pricing** | Top sibling-design pairs show 34–46× lift and 62–84% confidence | Attach rate and AOV on recommended pairs |
| 5 | **Use the weekly forecast for Q4 stock and staffing**; schedule campaigns for Tue–Thu late mornings | Nov is 1.8× average; orders peak Wed ~12:00 | Forecast WAPE; stock-outs in Q4 |
| 6 | **Root-cause cancellations in Spain and capture an ID on guest orders** | 13% cancellation rate; 13% of sales unattributable | Cancellation rate; share of sales with a customer ID |

## Caveats

- 2010 "new customer" figures are inflated by left-censoring (no history before Dec-2009).
- Revenue is GBP at invoice prices; no cost data, so CLV is revenue-, not margin-based.
- Basket rules are correlational: they say what is bought together, not what a recommendation would cause.
