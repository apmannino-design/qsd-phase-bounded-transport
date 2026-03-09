# QSD Cross-Domain Validation Report

## Included domains

- GOES solar X-ray flux
- Planetary K-index
- LIGO strain

## 1. Domain Comparison Summary

           domain  samples  deltaE_mean  eta_mean  hazard_mean  min_survival
 GOES Solar X-ray    10078     1.767666  0.536351     0.438799      0.200610
Planetary K-index      358     0.142683  0.915949     0.130940      0.304223

## 2. Surrogate Significance Summary

domain  eta_real  eta_null_mean  eta_percentile  eta_p_value
  GOES  0.536351       0.539379            0.03         0.97
    Kp  0.915949       0.773071            1.00         0.00
  LIGO  0.549949       0.548732            1.00         0.00

## 3. Spectral Null Summary (IAAFT)

domain  eta_real  eta_null_mean  eta_percentile  eta_p_value
  GOES  0.536351       0.543948            0.00         1.00
    Kp  0.915949       0.819905            1.00         0.00
  LIGO  0.549949       0.549461            0.82         0.18

## 4. Master Summary Table

           domain  samples  deltaE_mean  eta_mean  hazard_mean  min_survival  real_delta_e_mean  null_delta_e_mean_avg  real_eta_mean  null_eta_mean_avg  real_eta_min  null_eta_min_avg  real_vs_null_eta_mean_gap  real_vs_null_delta_e_gap
             GOES      NaN          NaN       NaN          NaN           NaN           1.767666               1.041261       0.536351           0.539370  0.000000e+00      1.303379e-99                  -0.003019                  0.726405
 GOES Solar X-ray  10078.0     1.767666  0.536351     0.438799      0.200610                NaN                    NaN            NaN                NaN           NaN               NaN                        NaN                       NaN
               Kp      NaN          NaN       NaN          NaN           NaN           0.142683               0.153732       0.915949           0.773751  8.514535e-53      3.294514e-03                   0.142198                 -0.011050
             LIGO      NaN          NaN       NaN          NaN           NaN           0.486928               0.517820       0.549949           0.548699  2.368040e-30      2.464708e-30                   0.001250                 -0.030891
Planetary K-index    358.0     0.142683  0.915949     0.130940      0.304223                NaN                    NaN            NaN                NaN           NaN               NaN                        NaN                       NaN

## 5. Reproducibility

Run the full pipeline with:

```bash
python3 scripts/run_all.py
```