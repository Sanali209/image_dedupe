import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

try:
    from core.database import DatabaseManager
    from core.deduper import Deduper
    from core.cluster_services import GraphBuilder, ClusterReconciler
    
    # Init DB
    db = DatabaseManager(":memory:")
    
    # Seed Data
    db.upsert_file("C:/dir/A.jpg", "hash1", 100, 100, 100, 1.0)
    db.upsert_file("C:/dir/B.jpg", "hash1", 100, 100, 100, 1.0) # Match A
    db.upsert_file("C:/dir/C.jpg", "hash2", 100, 100, 100, 1.0) # Distinct
    
    # Init Deduper
    deduper = Deduper(db)
    
    print("Deduper instantiated.")
    
    # Test Cluster Services Integration
    criteria = {'exact_hash': True}
    clusters = deduper.process_clusters(criteria)
    
    print(f"Clusters found: {len(clusters)}")
    if len(clusters) == 1 and len(clusters[0]['files']) == 2:
        print("Success: Correct clustering of A and B.")
    else:
        print(f"Failure: Expected 1 cluster, got {len(clusters)}")
        
except Exception as e:
    print(f"Verification Failed: {e}")
    sys.exit(1)
