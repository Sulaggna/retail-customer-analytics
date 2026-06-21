# Executive summary: retail customer & revenue analysis

Business: UK online giftware retailer, mostly selling to small wholesalers
Period: Dec 2009 to Dec 2011
Data: 1.07M raw transaction lines (1.00M clean sale lines), 39.5k orders, 5.9k customers, 4.9k products, 43 countries

## Main finding

Revenue is up a little: net revenue grew 1.9% to £9.33M in trading year 2011 (Dec-Nov). But the growth comes almost entirely from existing customers.

- Fewer new customers. Sales to first-time customers fell 54% year on year (Jan-Nov: £1.51M to £0.70M), and the number of first-time customers fell from 3,288 to 1,509. The 2010 figure is somewhat inflated because the data only starts in Dec 2009, but the decline is clear.
- Existing customers order less often. Orders per customer went from 4.29 to 4.11, which cost about £366k. Larger orders (+£155k), slightly more customers (+£105k) and guest checkouts (+£342k) made up for it this year.
- New customers stay less. Six months after their first order, 17% of the H1 2011 cohorts were still ordering, compared with 22% for H1 2010.

## Customers

| | |
|---|---|
| Revenue concentration | Top 20% of customers = 77% of revenue, top 1% = 31% |
| Champions (RFM) | 27% of customers, 72% of revenue, median 18 days since last order |
| At Risk + Can't Lose Them | 966 customers, £1.67M spent to date, £399k predicted revenue over the next 12 months |
| Time between orders | Median 32 days; 75% of repeat orders come within 70 days |
| Predicted revenue, next 12 months | £8.72M (BG/NBD + Gamma-Gamma model) |

I tested the lifetime value model on data it hadn't seen. It was fitted on Dec 2009 to Jun 2011 and predicted 7,605 purchases for the next 26 weeks. The actual number was 7,721 (1.5% off). Its per-customer error was 38% lower than simply extending each customer's past rate.

## Products and operations

- Customers buy sets. 88% of the 50 strongest product pairs are the same design in a different colour or variant. For example, 79-84% of people who buy one Poppy's Playhouse room also buy another (lift 42-46).
- 20% of products make up 78% of revenue.
- November alone is 1.8x an average month. The weekly forecast has a backtested error of 13.7%, 12% better than using the same week last year, so it's good enough for stock and staffing plans.
- Cancellations went up from 2.6% to 3.1% of gross sales. For Spain it's 13%.
- 13% of sales have no customer ID, so those customers can't be included in any customer analysis or targeting.

## Recommendations

| # | Action | Why | How to measure it |
|---|---|---|---|
| 1 | Make new-customer acquisition a tracked KPI and find out what changed in 2011 (channels, spend, range) | First-time sales halved | Monthly new customers and their month-1 and month-3 retention |
| 2 | Second-order campaign: reminder at day 30, offer at day 60 | Only ~21% of new customers come back in month 1, and the median gap between orders is 32 days | Month-1 retention, test group vs control (A/B test) |
| 3 | Account managers contact the 110 "Can't Lose Them" customers | They've spent £6.2k each on average, and the median repeat buyer in this group has a 38% chance of still being active | Share reactivated within 90 days |
| 4 | "Complete the set" recommendations and bundle pricing | The top design-sibling pairs have lift of 34-46 and confidence of 62-84% | Attach rate and order value on recommended pairs |
| 5 | Plan Q4 stock and staffing with the weekly forecast; run campaigns Tue-Thu late morning | November is 1.8x an average month; orders peak Wednesday around 12:00 | Forecast error, Q4 stock-outs |
| 6 | Look into Spanish cancellations and capture an ID on guest orders | 13% cancellation rate in Spain; 13% of sales can't be linked to a customer | Cancellation rate; share of sales with a customer ID |

## Caveats

- 2010 new-customer numbers are inflated because there's no history before Dec 2009.
- All values are revenue at invoice prices. There's no cost data, so lifetime value is revenue, not profit.
- Basket rules show what gets bought together. They don't show what a recommendation would cause.
