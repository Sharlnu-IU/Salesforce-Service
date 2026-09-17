from app.services.storage import StorageService
import os

def main():
    print("Testing MinIO Storage Service...")
    service = StorageService()
    
    files_to_upload = [
        "test_output/accounts.parquet",
        "test_output/account_addresses.parquet"
    ]
    
    for local_path in files_to_upload:
        if os.path.exists(local_path):
            object_name = f"normalized/account/{os.path.basename(local_path)}"
            print(f"Uploading {local_path} to {object_name}...")
            success = service.upload_file(local_path, object_name)
            if success:
                print(f"Upload successful: {object_name}")
            else:
                print(f"Upload failed: {object_name}")
        else:
            print(f"File not found: {local_path}")
            
    print("\nListing files in bucket 'normalized/':")
    files = service.list_files(prefix="normalized/")
    for f in files:
        print(f"- {f}")

if __name__ == "__main__":
    main()
