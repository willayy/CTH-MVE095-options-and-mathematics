# Low-Volatility Speculation using Bayesian Inference on 1-day Maturity European Cash-Settled Options

## Introduction

In daily life you often hear people speak about signs that the market will move down or up by a significant amount. In this project I wanted to explore a strategy based on predictions of neither of those events, but instead predictions about how little the stock will actually move every day.

## Methodology

### Gather historical HLOC data

Gather data from S&P500 and EUSTOXX600; to limit costly tail events we choose indexes for free diversification.

### Filter Data

Corporate action artifacts such as stock splits and ex-dividend jumps do not affect broad-market indices, as the index divisor dynamically absorbs them. Using modern 10-year electronic data directly from Interactive Brokers provides continuous, clean trade series with zero non-positive quotes or vendor placeholder artifacts.

### Exponentially discount samples

Data 10 years ago is worth less than data 10 days ago

### Model daily change

Model the daily change of the underlying asset price as a gaussian, assume that mean is 0,

### Model sigma

Learn sigma using bayesian inference

### Hierarchical model

Combine the learned sigma with the gaussian to create a hierarchical model for the distribution of the underlying asset price change.

### Derive strategy

Using this model we want to derive a price range of high probability, i then want to use a Short straddle to profit of this range, if the price breaks the range we will neutralize the position by buying or selling the underlying asset.

The underlying assumption here is that this method has a better measure of volatility than the market while simultaneously managing risk by neutralizing position if the bad event occurs.
