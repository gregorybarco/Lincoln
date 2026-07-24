# Lincoln Model Evaluation Report
Generated: 2026-07-24T03:10:05
Models: qwen3.5:9b, deepseek-r1:14b, gpt-oss:20b

## Summary

| Task | Model | Tokens/sec | VRAM delta (MB) | Processor | Tool call valid? |
|---|---|---|---|---|---|
| 1_domain_reasoning | qwen3.5:9b | 62.0 | 7036 | GB | - |
| 1_domain_reasoning | deepseek-r1:14b | 39.3 | 4216 | GB | - |
| 1_domain_reasoning | gpt-oss:20b | - | - | - | ERROR: 404 Client Error: Not Found for url: http://localhost:11434/api/chat |
| 2_tool_call_reliability | qwen3.5:9b | 63.6 | -4443 | GB | yes |
| 2_tool_call_reliability | deepseek-r1:14b | 39.7 | 4496 | GB | no tool call made |
| 2_tool_call_reliability | gpt-oss:20b | - | - | - | ERROR: 404 Client Error: Not Found for url: http://localhost:11434/api/chat |
| 3_python_coding | qwen3.5:9b | 62.3 | -4448 | GB | - |
| 3_python_coding | deepseek-r1:14b | 38.9 | 4464 | GB | - |
| 3_python_coding | gpt-oss:20b | - | - | - | ERROR: 404 Client Error: Not Found for url: http://localhost:11434/api/chat |
| 4_long_context | qwen3.5:9b | - | - | - | SKIPPED |
| 4_long_context | deepseek-r1:14b | - | - | - | SKIPPED |
| 4_long_context | gpt-oss:20b | - | - | - | SKIPPED |
| 5_sanity_check | qwen3.5:9b | 63.4 | -4448 | GB | - |
| 5_sanity_check | deepseek-r1:14b | 41.0 | 4448 | GB | - |
| 5_sanity_check | gpt-oss:20b | - | - | - | ERROR: 404 Client Error: Not Found for url: http://localhost:11434/api/chat |

---

## 1_domain_reasoning — Fortran / quant finance domain reasoning (PLACEHOLDER -- swap this prompt)

### qwen3.5:9b

**Response:**
```
In a quantitative finance codebase using standard Fortran conventions, the goal when computing Greeks via Finite Difference (FD) on the Black-Scholes formula is to achieve high numerical accuracy while maintaining stability. Standard libraries like BARCO or OptionsPricing typically use DOUBLE PRECISION (`REAL*8`) arithmetic and avoid magic constants in favor of configurable parameters derived from machine precision.

Here is how I would numerically compute these Greeks, followed by a sketch of the robust Fortran subroutine signature.

### Numerical Methodology: Central Difference Scheme

To minimize truncation error (which scales as $O(h^2)$), we use **Central Differences** rather than Forward/Backward differences ($O(h)$). This provides better convergence for smooth functions like the Black-Scholes price surface, provided we handle floating-point cancellation errors carefully.

Let $C(S, K, T, r, \sigma)$ be the Black-Scholes call option price function.
We define a perturbation magnitude step size ($h$) based on machine epsilon to ensure scale invariance (handling cases where Spot is 10 or 200). A robust rule of thumb for $S$-step is often derived from $\sqrt{\text{machine\_epsilon}} \times S$.

#### 1. Delta ($\Delta = \frac{\partial C}{\partial S}$)
We perturb the Spot price $S$ by a small amount $h_S$:
$$ \Delta_{num} \approx \frac{C(S + h_S, K, T, r, \sigma) - C(S - h_S, K, T, r, \sigma)}{2 h_S} $$

#### 2. Gamma ($\Gamma = \frac{\partial^2 C}{\partial S^2}$)
We compute the second derivative with respect to Spot using central differences of price:
$$ \Gamma_{num} \approx \frac{C(S + h_S, K, T, r, \sigma) - 2C(S, K, T, r, \sigma) + C(S - h_S, K, T, r, \sigma)}{h_S^2} $$
*Note: This effectively uses the curvature of the price smile.*

#### 3. Vega ($\mathcal{V} = \frac{\partial C}{\partial \sigma}$)
We perturb Volatility $\sigma$ by a step size $h_\Sigma$:
$$ \text{Vega}_{num} \approx \frac{C(S, K, T, r, \sigma + h_\Sigma) - C(S, K, T, r, \sigma - h_\Sigma)}{2 h_\Sigma} $$

**Optimization of Step Sizes:**
To satisfy "no hardcoded values," we calculate the optimal step size dynamically inside the subroutine using a generic function (e.g., `SQRT(REAL(KIND=8), EPSILON) * Input`), ensuring that $h$ is small enough for accuracy but large enough to avoid cancellation error.

---

### Fortran Subroutine Signature Sketch

The following sketch adheres to ASCII-127 constraints and assumes a modular design where the Black-Scholes price calculation `BS_CALL_PRICE` (or similar) can be called within this routine or is an inline subroutine. It utilizes standard naming conventions (`UPPER_CASE`, `_IN`/`_OUT`).

```fortran
SUBROUTINE COMPUTE_EUROPEAN_GREEKS( &
     SPOT, STRIKE, RATE, TIME_TO_MATURITY, VOLATILITY, & ! Inputs: Price variables
     H_SPOT, H_VOL, &                                     ! Configurable step sizes (optional)
     CALL_PRICE_RESULT, DELTA_NUM, GAMMA_NUM, VEGA_NUM )  ! Outputs

C-----------------------------------------------------------------------
C   COMPUTE_EUROPEAN_GREEKS
C   -----------------------------------------------------------------
C   Computes the Delta and Gamma of a European Call Option using 
C   Finite Differences on the BS Price. Vega is computed via FD w.r.t Vol.
C
C   Input:
C     SPOT    - Asset spot price (S)
C     STRIKE  - Strike price (K)
C     RATE    - Risk-free rate (r)
C     TIME_TO_MATURITY - Time to expiry in years (T)
C     VOLATILITY - Implied volatility (sigma)
C   Optional Inputs:
C     H_SPOT  - Step size for spot perturbation. If ZERO, computed 
C              dynamically based on machine epsilon and SPOT magnitude.
C     H_VOL   - Step size for vol perturbation.
C-----------------------------------------------------------------------

      IMPLICIT NONE
      
      REAL*8, INTENT(IN)       :: SPOT
      REAL*8, INTENT(IN)       :: STRIKE
      REAL*8, INTENT(IN)       :: RATE
      REAL*8, INTENT(IN)       :: TIME_TO_MATURITY
      REAL*8, INTENT(IN)       :: VOLATILITY
      
C     Allow user to override step sizes or leave as 0.0 for auto-calculation
      LOGICAL                  :: USE_DEFAULT_STEPS

      IF ( H_SPOT == ZERO .AND. H_VOL == ZERO ) THEN
         ! Logic: If zero passed, compute optimal h internally using 
         ! SQRT(REAL(KIND=8), EPSILON) * Input to avoid cancellation errors.
         ! This ensures the code works regardless of Spot magnitude (10 vs 200).
      END IF

C     Call Black-Scholes pricing function (assumed available in library)
C     C = BS_Price(S, K, T, r, sigma)
      
C-----------------------------------------------------------------------
C   CALCULATIONS
C-----------------------------------------------------------------------

! 1. Compute Base Price at S and Sigma
      CALL COMPUTE_BS_PRICE( SPOT, STRIKE, RATE, TIME_TO_MATURITY, &
                             VOLATILITY, PRICED_BASE ) 

! 2. Perturb Spot (S +/- h) for Delta and Gamma
C     We assume H_SPOT is provided or defaulted to ~1e-4 * S in a robust implementation
      
      CALL COMPUTE_BS_PRICE( SPOT + H_SPOT, STRIKE, RATE, TIME_TO_MATURITY, &
                             VOLATILITY, PRICED_UP ) 
      
      CALL COMPUTE_BS_PRICE( SPOT - H_SPOT, STRIKE, RATE, TIME_TO_MATURITY, &
                             VOLATILITY, PRICED_DOWN ) 

C     Delta = (P_up - P_down) / (2 * h_S)
      DELTA_NUM = (PRICED_UP - PRICED_DOWN) / ( 2.0D+0 * H_SPOT )

! 3. Compute Gamma using second order central difference on S
C     Gamma = [f(S+h) - 2*f(S) + f(S-h)] / h^2
      GAMMA_NUM = (PRICED_UP - 2.0D+0 * PRICED_BASE + PRICED_DOWN) &
                 / ( H_SPOT**2 )

! 4. Perturb Volatility for Vega
C     We assume H_VOL is provided or defaulted to ~1e-5
      
      CALL COMPUTE_BS_PRICE( SPOT, STRIKE, RATE, TIME_TO_MATURITY, &
                             VOLATILITY + H_VOL, PRICED_VOL_UP ) 
      
      CALL COMPUTE_BS_PRICE( SPOT, STRIKE, RATE, TIME_TO_MATURITY, &
                             VOLATILITY - H_VOL, PRICED_VOL_DOWN ) 

C     Vega = (P_vol_up - P_vol_down) / (2 * h_sigma)
! Note: Sometimes defined per 1% move. Here we return raw derivative w.r.t sigma.
      VEGA_NUM = (PRICED_VOL_UP - PRICED_VOL_DOWN) &
                / ( 2.0D+0 * H_VOL )

C-----------------------------------------------------------------------
    END SUBROUTINE COMPUTE_EUROPEAN_GREEKS
```
```

_tokens/sec: 62.0, VRAM: 1685 -> 8721 MB, processor: GB_

### deepseek-r1:14b

**Response:**
```
To compute the Greeks (Delta, Gamma, Vega) for a European call option using a finite-difference approach on the Black-Scholes formula in Fortran, follow these steps:

1. **Compute Option Price**: Use the Black-Scholes formula to calculate the option price at given parameters.

2. **Finite-Difference Perturbations**:
   - **Delta**: Perturb the stock price \( S \) and compute the change in option price.
   - **Gamma**: Use a second central difference on the option price with respect to \( S \).
   - **Vega**: Perturb the volatility \( \sigma \) and compute the change in option price.

3. **Subroutine Implementation**:
   - Define helper functions for the Black-Scholes formula and cumulative distribution.
   - Use finite differences to estimate each Greek efficiently.

Here is a Fortran subroutine implementing this approach:

```fortran
subroutine compute_greeks(S, K, r, T, sigma, Delta, Gamma, Vega)
    real S, K, r, T, sigma
    real Delta, Gamma, Vega

    ! Parameters for finite differences
    real, parameter :: delta_S_rel = 0.001  ! 0.1% perturbation
    real, parameter :: delta_sigma_rel = 0.01  ! 1% perturbation

    ! Compute option price at original parameters
    real C0 = compute_option_price(S, K, r, T, sigma)

    ! Calculate Delta (dC/dS)
    real S_up = S * (1 + delta_S_rel)
    real S_down = S * max(1 - delta_S_rel, 1e-8)  ! Avoid negative S
    real C_up = compute_option_price(S_up, K, r, T, sigma)
    real C_down = compute_option_price(S_down, K, r, T, sigma)

    Delta = (C_up - C_down) / (2 * delta_S_rel * S)

    ! Calculate Gamma (d²C/dS²)
    Gamma = (C_up - 2*C0 + C_down) / (delta_S_rel**2 * S**2)

    ! Calculate Vega (dC/dsigma)
    real sigma_up = sigma + delta_sigma_rel * sigma
    real sigma_down = sigma - delta_sigma_rel * sigma
    real C_sigma_up = compute_option_price(S, K, r, T, sigma_up)
    real C_sigma_down = compute_option_price(S, K, r, T, sigma_down)

    Vega = (C_sigma_up - C_sigma_down) / (2 * delta_sigma_rel * sigma)
end subroutine

! Helper function to compute option price using Black-Scholes
real function compute_option_price(S, K, r, T, sigma)
    real S, K, r, T, sigma
    real ln_S_K, numerator, denominator, d1, d2, N_d1, N_d2

    ln_S_K = log(S/K)
    numerator = ln_S_K + (r + 0.5 * sigma**2) * T
    denominator = sigma * sqrt(T)
    d1 = numerator / denominator
    d2 = d1 - denominator

    ! Compute cumulative normal distribution using error function approximation
    N_d1 = norm_cdf(d1)
    N_d2 = norm_cdf(d2)

    compute_option_price = S * N_d1 - K * exp(-r*T) * N_d2
end function

! Helper function for cumulative standard normal distribution
real function norm_cdf(x)
    real x
    real t, y
    if (x < 0.0) then
        t = 0.5 * (1.0 + erf(x / sqrt(2)))
    else
        t = 1.0 - 0.5 * (1.0 - erf(-x / sqrt(2)))
    end if
    norm_cdf = max(0.0, min(1.0, t))  ! Ensure within [0,1]
end function
```

**Explanation of the Code:**

- **compute_greeks Subroutine**: This subroutine calculates Delta, Gamma, and Vega using finite differences on the Black-Scholes model.
  
  - **Delta Calculation**: Perturbs the stock price by a small percentage (0.1%) and computes the change in option price to estimate sensitivity.
  
  - **Gamma Calculation**: Uses a second central difference on the option price with respect to the stock price to estimate the rate of change of Delta.
  
  - **Vega Calculation**: Perturbs volatility by 1% and computes the change in option price to estimate sensitivity.

- **compute_option_price Function**: Implements the Black-Scholes formula to calculate the theoretical price of a European call option. It uses `norm_cdf` to compute the cumulative distribution function for the standard normal distribution, which is approximated using the error function.

- **norm_cdf Function**: Provides an approximation of the cumulative distribution function for the standard normal distribution, ensuring values are within [0,1].

This approach efficiently computes the Greeks by leveraging finite-difference methods and avoids hardcoded values, adhering to BARCO/OptionsPricing conventions.
```

_tokens/sec: 39.3, VRAM: 8721 -> 12937 MB, processor: GB_

### gpt-oss:20b

**ERROR:** 404 Client Error: Not Found for url: http://localhost:11434/api/chat


## 2_tool_call_reliability — Agentic tool-call schema compliance

### qwen3.5:9b

**Tool calls:**
```json
[
  {
    "id": "call_jua6vh6e",
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

_tokens/sec: 63.6, VRAM: 12919 -> 8476 MB, processor: GB_

### deepseek-r1:14b

**Response:**
```
The Lincoln Ollama Service handles context window sizing by dividing documents into overlapping segments based on specified configuration settings. Here's a breakdown of how it works:

### Key Parameters:
1. **Context Length (`context_length`)**: Specifies the maximum number of tokens in each window.
2. **Stride (`stride`)**: Determines how many tokens to move forward after each window (default is 1, meaning no skipping).
3. **Overlap (`overlap`)**: The number of overlapping tokens between consecutive windows.
4. **Chunk Size (`chunk_size`)**: Influences the step size for moving between windows; if not set, defaults to 512.

### Process:
- **Initialization**: The `ContextWindowConfig` class sets default values for each parameter.
- **Window Generation**:
  - If context_length is -1, the entire text is treated as one window.
  - Otherwise, the document is split into multiple windows of size `context_length`.
  - Each subsequent window starts at a position determined by `(chunk_size - overlap) * stride`, ensuring overlapping as needed.

### Example Workflow:
For a 1024-token document with `context_length=512`, `stride=1`, and `overlap=64`:
- **Chunk Size**: Calculated as `min(512, 512 - 64) = 448`.
- **Windows**:
  1. First window: Tokens 0–511.
  2. Next start: 0 + (448 * 1) = 448 → Tokens 448–959.
  3. Next start: 448 + 448 = 896 → Tokens 896–1023.

This creates three overlapping windows, ensuring each subsequent window overlaps by 64 tokens with the previous one, allowing comprehensive coverage of the document while maintaining context up to the specified length.
```

_tokens/sec: 39.7, VRAM: 8476 -> 12972 MB, processor: GB_

### gpt-oss:20b

**ERROR:** 404 Client Error: Not Found for url: http://localhost:11434/api/chat


## 3_python_coding — General Python coding task

### qwen3.5:9b

**Response:**
```
```python
def max_drawdown(prices):
    """
    Calculate the maximum drawdown as a percentage from a list of prices.

    Maximum drawdown represents the largest peak-to-trough decline in value 
    over a period, expressed as a percentage. It is calculated as (peak - trough) / peak * 100
    at each point where the current price falls below the running maximum seen so far.

    Args:
        prices: List of float values representing sequential price points
        
    Returns:
        The maximum drawdown as a positive percentage value, or None if input is empty
    
    Examples:
        >>> max_drawdown([100, 95, 80])
        20.0
        >>> max_drawdown([100, 110, 90])
        18.18... (rounded to two decimal places)
    """
    
    if not prices:
        return None
    
    peak = prices[0]
    max_dd = 0.0
    
    for price in prices:
        # Update the running maximum/peak seen so far
        peak = max(peak, price)
        
        # Calculate current drawdown from the peak to this point's value
        dd = (price - peak) / peak * 100
        
        # Track the worst (most negative) drawdown encountered
        if dd < max_dd:
            max_dd = dd
    
    return abs(max_dd)


# Test cases for validation
if __name__ == "__main__":
    print(f"Test 1 - No decline: {max_drawdown([10, 20, 30])}")        # Output: None (no drawdown possible if only rising?) Actually this gives negative dd values. Let me reconsider the logic above!

# Correct version with simpler return of absolute max percentage drop
def correct_max_drawdown(prices):
    """Corrected implementation that returns maximum peak-to-trough decline."""
    
    if not prices:
        return None
    
    peak = prices[0]
    max_dd = 0.0
    
    for price in prices:
        # Update the running high (peak) seen so far
        if price > peak:
            peak = price
        
        # Calculate drawdown from current peak to this point's value
        dd = (price - peak) / peak * 100
        
        # Track maximum magnitude of decline (most negative dd, but stored as positive percentage)
        if abs(dd) > max_dd:
            max_dd = dd
    
    return abs(max_dd)


# Final clean version for production use
def calculate_max_drawdown(prices):
    """
    Calculate the maximum drawdown as a percentage from a list of prices.

    Maximum drawdown represents the largest peak-to-trough decline in value 
    over a period, expressed as a percentage. It is calculated as (peak - trough) / peak * 100
    at each point where the current price falls below the running maximum seen so far.

    Args:
        prices: List of float values representing sequential price points
        
    Returns:
        The maximum drawdown as a positive percentage value, or None if input is empty
    
    Examples:
        >>> calculate_max_drawdown([100, 95, 80])
        20.0
        >>> calculate_max_drawdown([100, 110, 90])
        ~18.18 (rounded to two decimal places)
    """

    if not prices:
        return None
    
    peak = prices[0]
    max_dd = 0.0
    
    for price in prices:
        # Update the running maximum/peak seen so far
        peak = max(peak, price)
        
        # Calculate current drawdown from the peak to this point's value (will be negative if below peak)
        dd = (price - peak) / peak * 100
        
        # Track worst drop encountered as positive percentage for return
        if abs(dd) > max_dd:
            max_dd = abs(dd)
    
    return round(max_dd, 2)


# Example usage and tests
if __name__ == "__main__":
    test_cases = [
        ([100.0, 95.0, 80.0], "Simple decline"),
        ([100.0, 110.0, 90.0], "Rise then fall"),
        ([100.0, 200.0, 180.0], "Large rise and partial recovery"),
        ( [], "Empty list" ),
    ]

    for prices, desc in test_cases:
        result = calculate_max_drawdown(prices)
        print(f"{desc}: {prices} -> Max Drawdown: {result:.2f}" if isinstance(result, float) else f"{desc}: {prices} -> Max Drawdown: None")
```

This version includes a clean implementation that correctly handles edge cases and provides example usage. The `calculate_max_drawdown` function computes the maximum drawdown as a positive percentage value or returns `None` for an empty list.
```

_tokens/sec: 62.3, VRAM: 12977 -> 8529 MB, processor: GB_

### deepseek-r1:14b

**Response:**
```
To solve this problem, we need to calculate the maximum drawdown from a given list of float prices. The maximum drawdown is defined as the peak-to-trough decline over a period, representing the largest drop from a previous high to a subsequent low in percentage terms.

### Approach
The approach involves iterating through each price point and treating it as a potential peak. For each peak, we then determine the minimum price that occurs after this peak until the end of the list. The drawdown is calculated as the percentage decline from the peak to this minimum price. We keep track of the maximum drawdown encountered during this process.

1. **Check for Edge Cases**: If the input list is empty or has fewer than two elements, return 0.0 since no drawdown can be computed.
2. **Iterate Through Each Price Point**: For each price point (treated as a potential peak), find the minimum price that occurs after this peak.
3. **Calculate Drawdown**: For each peak, compute the drawdown if there is a subsequent lower price. Track the maximum drawdown found.

### Solution Code
```python
def max_drawdown(prices):
    """Calculate the maximum drawdown as a percentage from a list of prices."""
    if not prices:
        return 0.0
    n = len(prices)
    if n < 2:
        return 0.0

    max_dd = 0.0

    for i in range(n - 1):  # Ensure there are elements after the current peak
        current_peak = prices[i]
        min_after = min(prices[j] for j in range(i + 1, n))
        if min_after < current_peak:
            dd = (current_peak - min_after) / current_peak * 100
            if dd > max_dd:
                max_dd = dd

    return round(max_dd, 2)
```

### Explanation
- **Edge Cases Handling**: The function first checks if the list is empty or has fewer than two elements and returns 0.0 immediately in such cases.
- **Iterating Through Prices**: For each price point (peak), the code looks ahead to find the minimum price that occurs after this peak. This ensures we capture all possible troughs following each peak.
- **Drawdown Calculation**: The drawdown is computed as a percentage decline from the peak to the trough. The maximum of these values is tracked and returned.

This approach efficiently handles the problem by ensuring each potential peak is evaluated against all subsequent prices, providing an accurate measure of the maximum drawdown in percentage terms.
```

_tokens/sec: 38.9, VRAM: 8529 -> 12993 MB, processor: GB_

### gpt-oss:20b

**ERROR:** 404 Client Error: Not Found for url: http://localhost:11434/api/chat


## 4_long_context — Long-context handling

### qwen3.5:9b

_Skipped: No --long-context-file was provided, so this task was skipped. Re-run with e.g. --long-context-file lincoln/lincoln_ollama_service.py for a real long-context test._

### deepseek-r1:14b

_Skipped: No --long-context-file was provided, so this task was skipped. Re-run with e.g. --long-context-file lincoln/lincoln_ollama_service.py for a real long-context test._

### gpt-oss:20b

_Skipped: No --long-context-file was provided, so this task was skipped. Re-run with e.g. --long-context-file lincoln/lincoln_ollama_service.py for a real long-context test._


## 5_sanity_check — Plain conversational sanity check

### qwen3.5:9b

**Response:**
```
A locally-run AI assistant is more privacy-preserving because all data processing happens directly on your device, meaning sensitive information never leaves your hardware without explicit permission. In contrast, cloud-based assistants must transmit queries and responses over the internet to remote servers, where that data can be logged by the provider, intercepted during transit, or potentially accessed/stored for third-party analysis.
```

_tokens/sec: 63.4, VRAM: 12993 -> 8545 MB, processor: GB_

### deepseek-r1:14b

**Response:**
```
A locally-run AI assistant offers enhanced privacy compared to cloud-based systems due to several factors:

1. **Data Retention**: Local AI processes data entirely on the user's device, preventing it from being transmitted elsewhere, thus avoiding potential interception risks.

2. **Reduced Transmission Risks**: Without sending data over the internet, there’s no exposure to network vulnerabilities or third-party surveillance.

3. **Third-Party Exposure**: Local systems minimize interaction with external entities, reducing the chance of unintended access or misuse by third parties.

4. **Control and Transparency**: Users have greater control over their data, including usage decisions and retention policies, unlike cloud services where data handling may be less transparent.

5. **Regulatory Compliance**: Local AI can facilitate adherence to privacy laws like GDPR, as users maintain jurisdictional control over their data.

6. **Data Minimization**: Local systems tend to process only necessary data, reducing the risk associated with accumulating unnecessary information.

While local AI may require more powerful hardware, its privacy benefits are substantial, offering a safer and more transparent alternative for data handling.
```

_tokens/sec: 41.0, VRAM: 8545 -> 12993 MB, processor: GB_

### gpt-oss:20b

**ERROR:** 404 Client Error: Not Found for url: http://localhost:11434/api/chat
