import pandas as pd
import numpy as np

print("=" * 60)
print("BASE DIARIA ETL - produccion_mes_actual.xlsx")
print("=" * 60)
df = pd.read_excel("etl/data/produccion_mes_actual.xlsx", sheet_name="produccion")
print(f"Filas: {len(df)} | Lotes: {df['LoteCompleto'].nunique()}")
print(f"\nCOLUMNAS ({len(df.columns)}):")
for i, c in enumerate(df.columns):
    not_null = df[c].notna().sum()
    pct = not_null / len(df) * 100
    sample = df[c].dropna().iloc[0] if not_null > 0 else "NaN"
    print(f"  {i+1:02d}. {c:<40} {pct:5.1f}%  sample={sample}")

print("\n" + "=" * 60)
print("COLUMNAS NUMERICAS CON BUENA COBERTURA (>50%)")
print("=" * 60)
numeric_cols = df.select_dtypes(include=[np.number]).columns
for c in numeric_cols:
    pct = df[c].notna().sum() / len(df) * 100
    if pct > 50:
        print(f"  {c:<40} {pct:5.1f}%  mean={df[c].mean():.3f}")
