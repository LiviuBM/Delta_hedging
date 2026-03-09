# Portfolio Shield Beginner Guide

This guide explains what the app does, why it exists, and how it builds a hedge recommendation in plain English.

## What The App Is

Portfolio Shield is a web app that looks at a stock portfolio and suggests option contracts that may reduce some of the portfolio's downside risk.

It is important to understand what it is **not**:

- It is not a brokerage.
- It does not place trades for the user.
- It does not guarantee that losses will be prevented.
- It does not promise that the recommended hedge will always behave perfectly.

The app is an **advisory tool**. It gives the user a structured recommendation and explains the trade-offs.

## The Core Idea In Simple Terms

If an investor owns stocks, those stocks can go down. One common way to reduce that downside risk is to buy **put options**.

A put option generally gains value when the underlying stock or market falls. Because of that, puts can act like insurance.

The app tries to answer questions like:

- "How much downside protection am I trying to buy?"
- "Should I hedge each stock separately, or use one market hedge like SPY?"
- "How much might this hedge cost?"
- "How much of my portfolio's downside sensitivity might it offset?"
- "When should I review the hedge again?"

## What Delta Means Here

The word **delta** is one of the main ideas behind the app.

In simple terms:

- Stock has a delta close to `+1`.
- A put option has a **negative** delta.
- If the stock falls, the put can gain value and offset part of the loss.

So when the app talks about **delta-based sizing**, it means:

- estimate how much positive stock exposure the portfolio has
- choose puts with negative delta
- size the number of contracts so the puts offset part of that exposure

This is why the app is called a delta-hedging advisory app.

## What The User Enters

The app asks the user for:

1. Portfolio positions
- ticker
- share count
- optional average cost

2. Protection target
- `Light`
- `Moderate`
- `Tight`

3. Advisory settings
- objective
- options experience
- hedge horizon in days
- premium budget

Each input changes the recommendation.

## What The Protection Levels Mean

The app uses three protection levels.

### Light

- targets about `25%` hedge coverage
- uses further out-of-the-money puts
- tries to be cheaper
- better for crash-style protection than tight day-to-day hedging

### Moderate

- targets about `50%` hedge coverage
- uses puts closer to the stock price
- balances cost and protection

### Tight

- targets about `100%` of the chosen delta coverage goal
- uses the closest strikes
- usually costs more
- is the most aggressive protection setting in the current app

Important: even the tight setting does **not** mean risk disappears. It just means the engine tries to offset a larger share of downside sensitivity.

## What The Objectives Mean

The user also chooses an objective. This helps the app decide which hedge style is the better fit.

### Reduce 1-3 Month Downside

This is the default general-purpose objective.

The app tries to find a reasonable middle ground between:

- hedge cost
- amount of protection
- option liquidity

### Protect Recent Gains

This leans more toward tighter protection. The app is more willing to favor a direct hedge on each stock if that gives a more precise fit.

### Crash Hedge Only

This leans toward cheaper disaster protection. The app is more willing to like a market-wide hedge, especially if one index hedge can cover a diversified portfolio more efficiently.

### Partial Delta Hedge

This is for users who want some hedge effect without paying for a stronger protection profile. The scoring logic gives more weight to keeping cost down.

## The Two Main Strategies The App Compares

The upgraded app compares two broad strategies.

### 1. Single-Name Protective Puts

This means:

- if the portfolio owns `AAPL`, `MSFT`, and `NVDA`
- the app looks for put options on `AAPL`, `MSFT`, and `NVDA`
- it sizes each hedge separately

Why use this approach:

- it matches each stock directly
- it is more specific
- it can be better for concentrated portfolios

Trade-offs:

- more contracts to manage
- usually more expensive than one broad market hedge
- can be harder for a beginner to monitor

### 2. Index Hedge

This means:

- instead of hedging every stock separately
- the app may use a broad market ETF option such as `SPY`

Why use this approach:

- simpler
- often more liquid
- can be more practical for diversified portfolios

Trade-offs:

- the hedge is less precise
- if a portfolio behaves very differently from the broad market, the hedge may not track perfectly

## How The App Chooses Between Those Strategies

The app does not just pick one style blindly.

It creates candidate recommendations and scores them.

The score is influenced by:

- premium cost as a percent of portfolio value
- how close the estimated coverage is to the selected protection target
- bid-ask spread
- fallback pricing risk
- whether the recommendation fits the user's stated budget
- the chosen objective
- the user's options experience

That means the app is trying to choose the **best fit**, not just the cheapest option or the highest-delta option.

## How Option Contracts Are Chosen

Once the app decides which approach to test, it still needs to choose actual contracts.

For each candidate put, it looks at things like:

- days to expiry
- strike price
- open interest
- bid and ask
- implied volatility
- estimated delta

It avoids contracts that look too hard to trade, for example:

- low open interest
- very wide bid-ask spreads
- prices that are too thin or unrealistic

## How The App Sizes A Hedge

The app uses delta-based sizing.

In plain English, the logic is:

1. Start with the stock exposure.
2. Decide how much of that exposure the user wants to hedge.
3. Find a put with a negative delta.
4. Divide the target exposure by the option's per-contract delta effect.
5. Round to a practical number of contracts.

For a single stock, the app roughly does:

- stock exposure = `shares`
- target hedge exposure = `shares * hedge percent`
- one put contract controls `100` shares
- the option delta tells the app how strong that put is

So if an option has a delta of about `-0.40`, one contract does not hedge a full `100` shares of stock exposure. It hedges only part of it. That is why more than one contract may be needed.

## What Happens If No Good Option Is Found

Sometimes the app may not find a liquid contract that passes the selection rules.

When that happens, the current app can fall back to an estimated option price using a simplified options model.

That is useful for keeping the app running, but it also means:

- the result is less reliable
- the app should warn the user
- the user should be more cautious with that recommendation

## What The Scenario Table Means

The results page includes simple scenarios such as:

- portfolio down `5%`
- portfolio down `10%`
- portfolio down `20%`
- portfolio up `5%`

For each scenario, the app shows:

- what the portfolio might be worth without the hedge
- what it might be worth with the hedge
- how much value the hedge adds in that scenario

These are **not forecasts**.

They are simplified "what if" checks designed to help the user understand the shape of the hedge.

## What The Review Triggers Mean

The app does not assume a hedge can be set once and ignored forever.

It gives review triggers such as:

- review if the portfolio moves by `5%` or more
- review after a set number of days
- review when the option gets too close to expiry

This matters because option hedges change over time.

The delta of a put today will not be the same later if:

- the stock price changes
- time passes
- volatility changes

## How The App Uses Portfolio Analytics

The app also shows extra analytics to help the user understand the portfolio itself:

- cost basis
- current value
- profit and loss
- allocation weights
- one-year portfolio history
- beta vs `SPY`

These analytics do not create the hedge by themselves, but they help the user understand:

- how concentrated the portfolio is
- whether an index hedge might make sense
- how much the portfolio tends to move with the broader market

## The Meaning Of Beta In This App

Beta is a rough measure of how much a portfolio moves compared with the market.

Examples:

- beta around `1.0` means "moves somewhat like the market"
- beta above `1.0` means "tends to move more than the market"
- beta below `1.0` means "tends to move less than the market"

The app uses this idea when evaluating an index hedge. If the portfolio's market sensitivity is higher or lower than average, the index hedge size can be adjusted.

## Why The App Asks About Budget And Experience

These are important retail-investor safety inputs.

### Budget

Hedges cost money. If the premium is too high, the app should say so.

The budget helps the app avoid recommendations that are obviously impractical.

### Experience

Two users may get the same contract recommendation, but not the same explanation.

A beginner should see stronger caution around:

- wide spreads
- fallback pricing
- near-expiry options
- order execution risk

## A Simple Example

Imagine the user enters:

- `100` shares of `AAPL`
- `50` shares of `MSFT`
- `Moderate` protection
- `45` day horizon
- budget of `$2,500`

The app then:

1. fetches the latest prices
2. calculates portfolio value
3. calculates analytics like weights and beta
4. tests a single-name hedge
5. tests an index hedge if the portfolio is diversified enough
6. scores both ideas
7. returns the better fit
8. shows the contracts, estimated cost, scenarios, and review rules

## What The Current Version Does Well

- keeps the old prototype preserved
- supports portfolio-level thinking
- compares two hedge styles
- explains the recommendation better than before
- gives scenario views and review triggers
- stores recommendation records locally

## What The Current Version Does Not Yet Do Perfectly

The app is still an MVP. It does **not** yet do all of the things a production-grade hedge platform would need.

Examples of current limitations:

- no advanced mixed hedge optimizer
- no full Greeks engine beyond the delta-centered sizing logic
- simplified scenarios
- prototype market-data dependency
- no guarantee of hedge quality in stressed conditions

## Short Beginner Summary

If you want the shortest possible explanation:

- the user enters a stock portfolio
- the app estimates downside exposure
- the app looks for put options that could offset part of that downside
- it compares different hedge styles
- it recommends one approach
- it explains the cost, the likely protection effect, and when to review it again

That is the app in one sentence:

**Portfolio Shield is a beginner-friendly advisory tool that uses delta-based option sizing to suggest protective hedges for a stock portfolio.**
