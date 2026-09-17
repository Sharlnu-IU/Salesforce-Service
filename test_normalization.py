import pandas as pd
from app.services.normalization.service import NormalizationService

def main():
    csv_file = "account_export_750g800000IQltlAAD.csv"
    print(f"Testing normalization on {csv_file}")
    
    # 1. Initialize service
    service = NormalizationService(output_dir="test_output")
    
    # 2. Normalize
    parquet_files = service.normalize_csv(object_name="Account", csv_filepath=csv_file)
    
    print("\nNormalization complete. Output files:")
    for pf in parquet_files:
        print(f"- {pf}")
        
    print("\nVerifying Parquet contents:")
    for pf in parquet_files:
        print(f"\n--- {pf} ---")
        df = pd.read_parquet(pf)
        print(df.to_string(index=False))

if __name__ == "__main__":
    main()
