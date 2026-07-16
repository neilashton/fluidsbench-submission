# Reference metric implementation

Participants own their model inference, data loading, dimensionalisation, mesh alignment, and profile extraction. The functions
in [`metrics.py`](metrics.py) define the numerical reductions once aligned NumPy arrays are available. They do not prescribe a
participant's input file format.

## Common equations

For ground truth \(y_i\), prediction \(\hat y_i\), and non-negative physical weights \(w_i\):

\[
\operatorname{MSE}_w = \frac{\sum_i w_i(\hat y_i-y_i)^2}{\sum_i w_i}
\]

\[
\operatorname{MAE}_w = \frac{\sum_i w_i |\hat y_i-y_i|}{\sum_i w_i}
\]

\[
\operatorname{RMSE}_w = \sqrt{\frac{\sum_i w_i(\hat y_i-y_i)^2}{\sum_i w_i}}
\]

\[
L_{1,\mathrm{rel}}(\%) = 100\frac{\sum_i w_i|\hat y_i-y_i|}{\sum_i w_i|y_i|}
\]

\[
L_{2,\mathrm{rel}}(\%) = 100\frac{\sqrt{\sum_i w_i(\hat y_i-y_i)^2}}{\sqrt{\sum_i w_i y_i^2}}
\]

\[
R^2_w = 1-\frac{\sum_i w_i(y_i-\hat y_i)^2}{\sum_i w_i(y_i-\bar y_w)^2},\qquad
\bar y_w=\frac{\sum_iw_i y_i}{\sum_iw_i}
\]

Surface metrics use face-area weights and volume metrics use cell-volume weights when those physical measures are part of the
dataset contract. Coefficient metrics normally use equal case weights. Dataset specifications state whether a metric is computed
globally or per geometry followed by a macro-average. Macro-averaging is the default for field metrics so each test geometry has
equal influence regardless of mesh resolution.

For per-geometry values \(m_k\), the macro-average over \(K\) test geometries is:

\[
\bar m = \frac{1}{K}\sum_{k=1}^{K}m_k
\]

Vector quantities must include every declared component. Apply the same physical weight to each component and flatten the
component axis before evaluating the norm unless the dataset specification states another reduction.

Inputs must be dimensional where the metric unit is dimensional. The functions reject empty arrays, non-finite numbers, negative
weights, zero total weight, zero relative-error denominators, and constant-ground-truth R2 rather than silently inventing a value.

VKI-LS59 and Rotor37 additionally use the following benchmark-specific RRMSE equations. For field case \(k\) with
\(N_k\) values:

\[
\operatorname{RRMSE}_{field} = \sqrt{\frac{1}{K}\sum_{k=1}^{K}
\frac{\lVert\hat{\mathbf y}_k-\mathbf y_k\rVert_2^2/N_k}{\lVert\mathbf y_k\rVert_\infty^2}}
\]

For scalar outputs:

\[
\operatorname{RRMSE}_{scalar} = \sqrt{\frac{1}{K}\sum_{k=1}^{K}
\frac{|\hat y_k-y_k|^2}{|y_k|^2}}
\]

## Benchmark scores

[`scores.py`](scores.py) implements the prototype external-aerodynamics score and arithmetic aggregate used by the turbine
datasets and BlendedNet. For the four field errors \(e_j\), caps \(c_j=(15,20,12,15)\), and weights
\(w_j=(0.15,0.10,0.15,0.10)\):

\[
S_{field}=\frac{\sum_j w_j\,\operatorname{clip}(100(1-e_j/c_j),0,100)}{0.50}
\]

\[
S_{force}=\frac{0.15\,\operatorname{clip}(R^2_{C_D},0,1)100+
0.10\,\operatorname{clip}(R^2_{C_L},0,1)100}{0.25}
\]

\[
S_{profile}=\frac{0.15\,\operatorname{clip}(R^2_{velocity},0,1)100+
0.10\,\operatorname{clip}(R^2_{C_p},0,1)100}{0.25}
\]

\[
S_{overall}=0.50S_{field}+0.25S_{force}+0.25S_{profile}
\]

These score caps and weights remain prototype policy until the dataset owners approve them. Dataset-specific aggregate metrics use
the unweighted arithmetic mean of the exact source metric IDs listed in `submission-spec.json`.

Run the array-level example from the repository root with:

```bash
python3 -m reference.example_calculation
```
