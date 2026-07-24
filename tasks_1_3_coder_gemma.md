# Lincoln Model Evaluation Report
Generated: 2026-07-24T04:25:43
Models: qwen2.5-coder:latest, gemma4:12b

## Summary

| Task | Model | Tokens/sec | VRAM delta (MB) | Processor | Tool call valid? |
|---|---|---|---|---|---|
| 1_domain_reasoning | qwen2.5-coder:latest | 76.4 | -9 | 100% GPU     16384 | - |
| 1_domain_reasoning | gemma4:12b | 41.5 | 3374 | 100% GPU     16384 | - |
| 2_tool_call_reliability | qwen2.5-coder:latest | 75.4 | -3198 | 100% GPU     16384 | no tool call made |
| 2_tool_call_reliability | gemma4:12b | 43.4 | 3190 | 100% GPU     16384 | yes |
| 3_python_coding | qwen2.5-coder:latest | 77.2 | -3178 | 100% GPU     16384 | - |
| 3_python_coding | gemma4:12b | 42.2 | -858 | 100% GPU     16384 | - |

---

## 1_domain_reasoning — Fortran / quant finance domain reasoning (PLACEHOLDER -- swap this prompt)

### qwen2.5-coder:latest

**Response:**
```
To numerically compute the Greeks (Delta, Gamma, and Vega) for a European call option using a finite-difference approach based on the Black-Scholes model in FORTRAN (with ASCII-127 source only), follow these steps:

### 1. Understand the Black-Scholes Formula

The Black-Scholes formula for a European call option is given by:

\[ C(S, t) = S N(d_1) - Ke^{-r(T-t)} N(d_2) \]

where:
- \( C(S, t) \) is the price of the call option
- \( S \) is the stock price
- \( K \) is the strike price
- \( r \) is the risk-free interest rate
- \( T \) is the time to maturity
- \( N(x) \) is the cumulative distribution function (CDF) of the standard normal distribution
- \( d_1 = \frac{\ln(S/K) + (r + \sigma^2/2)(T-t)}{\sigma\sqrt{T-t}} \)
- \( d_2 = d_1 - \sigma\sqrt{T-t} \)

### 2. Define the Finite-Difference Approach

To compute the Greeks, you need to take partial derivatives of the Black-Scholes formula with respect to the relevant variables (stock price \( S \), time to maturity \( T \), volatility \( \sigma \)).

#### Delta:
\[ \Delta = \frac{\partial C}{\partial S} = N(d_1) \]

#### Gamma:
\[ \Gamma = \frac{\partial^2 C}{\partial S^2} = \frac{N'(d_1)}{S\sigma\sqrt{T-t}} \]
where \( N'(x) \) is the probability density function (PDF) of the standard normal distribution.

#### Vega:
\[ \text{Vega} = \frac{\partial C}{\partial \sigma} = S \sqrt{T-t} N'(d_1) \]

### 3. Implement Finite-Difference Approximations

To approximate these derivatives numerically, you can use central differences:

- For Delta (with respect to \( S \)):
\[ \Delta_{FD} = \frac{C(S + \epsilon, T) - C(S - \epsilon, T)}{2\epsilon} \]

- For Gamma (with respect to \( S \)):
\[ \Gamma_{FD} = \frac{\Delta(S + \epsilon, T) - \Delta(S - \epsilon, T)}{2\epsilon} \]

- For Vega (with respect to \( \sigma \)):
\[ \text{Vega}_{FD} = \frac{C(S, T, \sigma + \epsilon) - C(S, T, \sigma - \epsilon)}{2\epsilon} \]

where \( \epsilon \) is a small perturbation.

### 4. Fortran Subroutine Signature

Here's a sketch of how you might define the subroutine in FORTRAN:

```fortran
subroutine compute_greeks(s, k, r, t, sigma, delta, gamma, vega)
    ! Arguments
    real :: s       ! Stock price
    real :: k       ! Strike price
    real :: r       ! Risk-free interest rate
    real :: t       ! Time to maturity (years)
    real :: sigma   ! Volatility

    ! Output Greeks
    real, intent(out) :: delta
    real, intent(out) :: gamma
    real, intent(out) :: vega

    ! Local variables
    real :: epsilon = 1.0e-4  ! Small perturbation
    real :: c_s_plus, c_s_minus, c_sigma_plus, c_sigma_minus
    real :: d1, d2, n_d1, n_d2, pdf_d1

    ! Compute Black-Scholes values
    call black_scholes(s, k, r, t, sigma, n_d1, n_d2)

    ! Compute Greeks using finite-difference
    c_s_plus = black_scholes(S + epsilon, K, R, T, Sigma)
    c_s_minus = black_scholes(S - epsilon, K, R, T, Sigma)
    delta = (c_s_plus - c_s_minus) / (2 * epsilon)

    gamma = (delta(S + epsilon, T) - delta(S - epsilon, T)) / (2 * epsilon)

    call black_scholes(s, k, r, t, sigma, d1, d2)
    pdf_d1 = normal_pdf(d1)
    c_sigma_plus = black_scholes(S, K, R, T, Sigma + epsilon)
    c_sigma_minus = black_scholes(S, K, R, T, Sigma - epsilon)
    vega = S * sqrt(T) * pdf_d1 * (c_sigma_plus - c_sigma_minus) / (2 * epsilon)

end subroutine compute_greeks

subroutine black_scholes(s, k, r, t, sigma, n_d1, n_d2)
    ! Arguments
    real :: s       ! Stock price
    real :: k       ! Strike price
    real :: r       ! Risk-free interest rate
    real :: t       ! Time to maturity (years)
    real :: sigma   ! Volatility

    ! Output Black-Scholes values
    real, intent(out) :: n_d1
    real, intent(out) :: n_d2

    ! Local variables
    real :: d1, d2

    ! Compute d1 and d2
    d1 = (log(s / k) + (r + 0.5 * sigma ** 2) * t) / (sigma * sqrt(t))
    d2 = d1 - sigma * sqrt(t)

    ! Compute N(d1) and N(d2)
    n_d1 = normal_cdf(d1)
    n_d2 = normal_cdf(d2)

end subroutine black_scholes

real function normal_cdf(x)
    real, intent(in) :: x
    ! Implementation of the cumulative distribution function for the standard normal distribution
end function normal_cdf

real function normal_pdf(x)
    real, intent(in) :: x
    ! Implementation of the probability density function for the standard normal distribution
end function normal_pdf
```

### 5. Notes:
- The `normal_cdf` and `normal_pdf` functions need to be implemented based on standard normal distribution formulas.
- Ensure that all inputs are valid (e.g., \( \sigma > 0 \), \( T > 0 \)).
- The choice of \( \epsilon \) is important; it should balance the accuracy and numerical stability.

This subroutine provides a basic framework for numerically computing Delta, Gamma, and Vega using finite-differences based on the Black-Scholes model in FORTRAN. Adjustments may be needed depending on specific requirements or constraints of your project.
```

_tokens/sec: 76.4, VRAM: 10791 -> 10782 MB, processor: 100% GPU     16384_

### gemma4:12b

**Response:**
```
To adhere to the **BARCO/OptionsPricing** standards, the implementation must prioritize modularity, precision, and strict separation between the mathematical model and the calculation logic. Since no hardcoded values are permitted, all parameters—including the "bumps" used for finite differences—must be passed as arguments or defined in a configuration structure.

### 1. Numerical Approach: Finite Difference Method (FDM)

Since we are calculating Greeks for a European option where an analytical solution (Black-Scholes) exists, we use **Central Difference** approximations. Central differences are preferred over forward/backward differences because they provide $O(h^2)$ accuracy rather than $O(h)$.

#### The Formulas:
1.  **Delta ($\Delta$):** Measures sensitivity to the underlying price ($S$).
    $$\Delta \approx \frac{V(S + \Delta S) - V(S - \Delta S)}{2\Delta S}$$
2.  **Gamma ($\Gamma$):** Measures the second derivative of the option price with respect to $S$.
    $$\Gamma \approx \frac{V(S + \Delta S) - 2V(S) + V(S - \Delta S)}{(\Delta S)^2}$$
3.  **Vega ($\nu$):** Measures sensitivity to volatility ($\sigma$).
    $$\nu \approx \frac{V(\sigma + \Delta\sigma) - V(\sigma - \Delta\sigma)}{2\Delta\sigma}$$

#### Implementation Strategy:
*   **The "Bump" Logic:** To avoid hardcoding, $\Delta S$ and $\Delta \sigma$ should be calculated as a percentage of the current value (e.g., $0.1\%$ of $S$) or passed as absolute values from a configuration file. 
*   **Method Decoupling:** The Greek calculation logic should not "know" it is using Black-Scholes. It should call a generic `PriceOption` routine. This allows the same Greek engine to work for Binomial trees, Monte Carlo, or other models by simply swapping the pricing subroutine.

---

### 2. Fortran Implementation Details

Following the **ASCII-127** and **No Hardcoded Values** constraints:
*   Use `REAL*8` (or `DOUBLE PRECISION`) for all calculations to maintain precision.
*   Encapsulate the Greek logic in a dedicated subroutine.
*   The "Bump" sizes are passed as parameters or retrieved from a configuration structure.

#### The Subroutine Signature

In this architecture, I would separate the **Price Engine** (the math) from the **Greek Calculator** (the calculus).

```fortran
! ----------------------------------------------------------------------------
! MODULE: OptionsPricing_Core
! PURPOSE: Provide core pricing functions for European options.
! ----------------------------------------------------------------------------
MODULE OptionsPricing_Core
    IMPLICIT NONE
    INTEGER, PARAMETER :: KIND = SELECTED_REAL_UNIT (8)
    REAL*K_TYPE :: REAL_TYPE = REAL(KIND=8)

CONTAINS

    ! Standard Black-Scholes Pricing Routine
    ! This function is agnostic of the Greeks; it only calculates price.
    SUBROUTINE CalculatePrice(S, K, T, r, sigma, type, price)
        USE OptionsPricing_Core
        IMPLICIT NONE
        REAL*K_TYPE, INTENT(IN)  :: S, K, T, r, sigma
        INTEGER, INTENT(IN)       :: type      ! 1 = Call, 2 = Put
        REAL*K_TYPE, INTENT(OUT)  :: price
        
        ! Implementation of Black-Scholes formula...
    END SUBROUTINE CalculatePrice

END MODULE OptionsPricing_Core

! ----------------------------------------------------------------------------
! SUBROUTINE: ComputeGreeks
! PURPOSE: Compute Delta, Gamma, and Vega using Finite Difference.
! CONVENTIONS: No hardcoded values; uses central difference for O(h^2).
! ----------------------------------------------------------------------------
SUBROUTINE ComputeGreeks(S, K, T, r, sigma, 
                         delta, gamma, vega, 
                         ds_bump, dsigma_bump)
    USE OptionsPricing_Core
    IMPLICIT NONE
    
    ! Input Parameters
    REAL*K_TYPE, INTENT(IN)  :: S, K, T, r, sigma
    REAL*K_TYPE, INTENT(IN)  :: ds_bump, dsigma_bump ! These are the 'h' values
    
    ! Output Greeks
    REAL*K_TYPE, INTENT(OUT)  :: delta, gamma, vega
    
    ! Internal variables for pricing at shifted points
    REAL*K_TYPE :: p_plus, p_minus, p_mid
    
    ! 1. Calculate Delta (Central Difference)
    ! Delta = [V(S + dS) - V(S - dS)] / (2 * dS)
    CALL CalculatePrice(S + ds_bump, K, T, r, sigma, 1, p_plus)
    CALL CalculatePrice(S - ds_bump, K, T, r, sigma, 1, p_minus)
    delta = (p_plus - p_minus) / (2.0 * ds_bump)
    
    ! 2. Calculate Gamma (Central Difference)
    ! Gamma = [V(S + dS) - 2*V(S) + V(S - dS)] / (dS^2)
    CALL CalculatePrice(S, K, T, r, sigma, 1, p_mid)
    gamma = (p_plus - 2.0 * p_mid + p_minus) / (ds_bump**2)
    
    ! 3. Calculate Vega (Central Difference)
    ! Vega = [V(sigma + dSigma) - V(sigma - dSigma)] / (2 * dSigma)
    CALL CalculatePrice(S, K, T, r, sigma + dsigma_bump, 1, p_plus)
    CALL CalculatePrice(S, K, T, r, sigma - dsigma_bump, 1, p_minus)
    vega = (p_plus - p_minus) / (2.0 * dsigma_bump)

END SUBROUTINE ComputeGreeks
```

### Key Architectural Decisions Explained:

1.  **Separation of Concerns:** By calling `CalculatePrice` three times inside the Greek routine, we ensure that if the underlying pricing model changes (e.g., moving from Black-Scholes to a Heston Model), the `ComputeGreeks` subroutine remains untouched.
2.  **No Hardcoding:** Notice `ds_bump` and `dsigma_bump` are inputs. In a production environment, these would be pulled from a config file (e.g., `0.01` for 1% move) rather than being hardcoded as `0.01` inside the code.
3.  **Precision:** Using `REAL*K_TYPE` ensures that we maintain consistent precision across all calculations, which is critical when calculating Gamma (where the denominator is $ds^2$, potentially leading to floating-point issues if $ds$ is too small).
4.  **Complexity:** The time complexity is $O(1)$ as we are performing a fixed number of evaluations to find the Greeks for a single point.
```

_tokens/sec: 41.5, VRAM: 10782 -> 14156 MB, processor: 100% GPU     16384_


## 2_tool_call_reliability — Agentic tool-call schema compliance

### qwen2.5-coder:latest

**Response:**
```
{"name": "read_file", "arguments": {"path": "lincoln_ollama_service.py"}}
```

_tokens/sec: 75.4, VRAM: 14156 -> 10958 MB, processor: 100% GPU     16384_

### gemma4:12b

**Tool calls:**
```json
[
  {
    "id": "call_eby2ohy9",
    "function": {
      "index": 0,
      "name": "read_file",
      "arguments": {
        "path": "lincoln_ollama_service.py"
      }
    }
  }
]
```

**Response:**
```

```

_tokens/sec: 43.4, VRAM: 10958 -> 14148 MB, processor: 100% GPU     16384_


## 3_python_coding — General Python coding task

### qwen2.5-coder:latest

**Response:**
```
```python
def calculate_max_drawdown(prices):
    """
    Calculate the maximum drawdown in percentage from a list of stock prices.

    Args:
    prices (list of float): A list of float numbers representing stock prices over time.

    Returns:
    float: The maximum drawdown as a percentage. If the input list is empty, returns 0.
    
    Example:
    >>> calculate_max_drawdown([100, 85, 95, 75, 80])
    25.0
    """
    if not prices:
        return 0
    
    max_price = max(prices)
    drawdowns = [(max_price - price) / max_price * 100 for price in prices]
    max_drawdown = min(drawdowns)
    
    return abs(max_drawdown)

# Check function with the provided data points
def check_function():
    assert calculate_max_drawdown([100, 85, 95, 75, 80]) == 25.0, "Test case 1 failed"
    assert calculate_max_drawdown([10, 15, 5, 20]) == -20.0, "Test case 2 failed"
    assert calculate_max_drawdown([]) == 0, "Test case 3 (empty list) failed"

check_function()
```

This Python solution adheres to the guidelines provided, offering a concise and clear implementation of the `calculate_max_drawdown` function with an emphasis on readability and efficiency. The check function is included to validate the correctness of the solution against different scenarios, including edge cases like an empty input list.
```

_tokens/sec: 77.2, VRAM: 14148 -> 10970 MB, processor: 100% GPU     16384_

### gemma4:12b

**Response:**
```
Here is the Python function to calculate the maximum drawdown.

```python
from typing import List

def calculate_max_drawdown(prices: List[float]) -> float:
    """
    Calculates the maximum drawdown of a price series as a percentage.
    
    The maximum drawdown is the maximum observed loss from a peak to a 
    subsequent trough in the price history.

    Args:
        prices (List[float]): A list of historical prices.

    Returns:
        float: The maximum drawdown expressed as a percentage (e.g., 15.0 for 15%).
                Returns 0.0 if the list is empty or contains only one price.
    """
    if not prices or len(prices) < 2:
        return 0.0

    max_drawdown = 0.0
    peak = -float('inf')

    for price in prices:
        # Update the peak if the current price is higher than the previous peak
        if price > peak:
            peak = price
        else:
            # Calculate drawdown from the peak as a decimal (e.g., 0.1 for 10%)
            drawdown = (peak - price) / peak
            if drawdown > max_drawdown:
                max_drawdown = drawdown

    return max_drawdown * 100

# Example Usage:
if __name__ == "__main__":
    prices_list = [100.0, 110.0, 105.0, 120.0, 110.0, 90.0]
    mdd = calculate_max_drawdown(prices_list)
    print(f"Maximum Drawdown: {mdd:.2f}%")  # Output should be 25.00% (from 120 to 90)
```

### Explanation of the Logic:
1.  **Edge Case Handling:** The function first checks if the list is empty or contains only one price point. In these cases, no "drop" can occur, so it returns `0.0`.
2.  **Tracking the Peak:** As we iterate through the list, we keep track of the highest price seen *so far* (`peak`). 
3.  **Calculating Drawdown:** Every time the current price is lower than the peak, we calculate what percentage that drop represents relative to the peak: $\frac{\text{Peak} - \text{Current}}{\text{Peak}}$.
4.  **Updating Maximum:** We compare the current drawdown against the highest one recorded during the loop and update `max_drawdown` if the current one is larger.
5.  **Percentage Conversion:** Finally, it multiplies by 100 to convert the decimal (e.g., $0.25$) into a percentage format ($25.0$).
```

_tokens/sec: 42.2, VRAM: 10970 -> 10112 MB, processor: 100% GPU     16384_
