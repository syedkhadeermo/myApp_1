import requests
import unittest
import os
import json
import tempfile
import numpy as np
import h5py
import anndata
import pandas as pd
from pathlib import Path

# Use the public endpoint from the frontend .env file
BACKEND_URL = "https://5917b2fa-c816-4890-9b71-d4cc854ac113.preview.emergentagent.com/api"

class TestScRNASeqAPI(unittest.TestCase):
    """Test suite for the scRNA-seq Ligand Effect Prediction API"""
    
    def setUp(self):
        """Set up test variables"""
        self.api_url = BACKEND_URL
        self.analysis_id = None
        
        # Example SMILES strings for testing
        self.smiles_examples = [
            "CC(=O)OC1=CC=CC=C1C(=O)O",  # Aspirin
            "CN1C=NC2=C1C(=O)N(C(=O)N2C)C",  # Caffeine
            "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O",  # Ibuprofen
            "CC(=O)NC1=CC=C(C=C1)O"  # Paracetamol
        ]
        
        # Example organs for testing
        self.organs = [
            "liver", "lung", "heart", "brain", "kidney", 
            "muscle", "bone", "skin"
        ]
        
        # Create a mock H5AD file for testing
        self.mock_h5ad_path = self.create_mock_h5ad()
    
    def create_mock_h5ad(self):
        """Create a small mock H5AD file for testing"""
        try:
            # Create a temporary file
            fd, path = tempfile.mkstemp(suffix='.h5ad')
            os.close(fd)
            
            # Create a small AnnData object
            n_obs = 20  # 20 cells
            n_vars = 50  # 50 genes
            
            # Random data
            X = np.random.rand(n_obs, n_vars)
            obs = pd.DataFrame(index=[f'cell_{i}' for i in range(n_obs)])
            var = pd.DataFrame(index=[f'gene_{i}' for i in range(n_vars)])
            
            # Create AnnData object
            adata = anndata.AnnData(X=X, obs=obs, var=var)
            
            # Save to file
            adata.write(path)
            
            print(f"Created mock H5AD file at {path}")
            return path
        
        except Exception as e:
            print(f"Failed to create mock H5AD file: {str(e)}")
            return None
    
    def tearDown(self):
        """Clean up after tests"""
        if self.mock_h5ad_path and os.path.exists(self.mock_h5ad_path):
            os.remove(self.mock_h5ad_path)
    
    def test_01_root_endpoint(self):
        """Test the root endpoint"""
        print("\n🔍 Testing root endpoint...")
        response = requests.get(f"{self.api_url}/")
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("message", data)
        self.assertIn("version", data)
        print("✅ Root endpoint test passed")
    
    def test_02_health_endpoint(self):
        """Test the health check endpoint"""
        print("\n🔍 Testing health check endpoint...")
        response = requests.get(f"{self.api_url}/health")
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("status", data)
        self.assertIn("timestamp", data)
        self.assertIn("services", data)
        self.assertEqual(data["status"], "healthy")
        print("✅ Health check test passed")
    
    def test_03_upload_h5ad(self):
        """Test the H5AD file upload endpoint"""
        print("\n🔍 Testing H5AD file upload...")
        
        if not self.mock_h5ad_path:
            self.skipTest("Mock H5AD file creation failed")
        
        try:
            with open(self.mock_h5ad_path, 'rb') as f:
                files = {'file': ('test_data.h5ad', f, 'application/octet-stream')}
                response = requests.post(f"{self.api_url}/upload-h5ad", files=files)
            
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertIn("analysis_id", data)
            self.assertIn("n_cells", data)
            self.assertIn("n_genes", data)
            
            # Save analysis_id for subsequent tests
            self.analysis_id = data["analysis_id"]
            print(f"✅ File upload test passed. Analysis ID: {self.analysis_id}")
            
        except Exception as e:
            print(f"❌ File upload test failed: {str(e)}")
            self.fail(f"File upload test failed: {str(e)}")
    
    def test_04_predict_endpoint(self):
        """Test the prediction endpoint"""
        print("\n🔍 Testing prediction endpoint...")
        
        # Skip if we don't have an analysis_id from the upload test
        if not self.analysis_id:
            print("⚠️ Skipping prediction test as no analysis_id is available")
            # Use a mock analysis_id for testing
            self.analysis_id = "00000000-0000-0000-0000-000000000000"
        
        # Test with each SMILES example and a random organ
        for smiles in self.smiles_examples[:1]:  # Just test one for speed
            organ = self.organs[0]  # Use liver
            
            payload = {
                "smiles": smiles,
                "organ": organ,
                "analysis_id": self.analysis_id
            }
            
            try:
                response = requests.post(f"{self.api_url}/predict", json=payload)
                
                # Print response details for debugging
                print(f"Response status code: {response.status_code}")
                print(f"Response content: {response.text}")
                
                # If the analysis_id doesn't exist, we expect a 404 or 500
                if self.analysis_id == "00000000-0000-0000-0000-000000000000":
                    self.assertIn(response.status_code, [404, 500])
                    print("✅ Prediction correctly returned error for invalid analysis_id")
                else:
                    self.assertEqual(response.status_code, 200)
                    data = response.json()
                    self.assertIn("id", data)
                    self.assertIn("analysis_id", data)
                    self.assertIn("affected_genes", data)
                    self.assertIn("potential_cures", data)
                    self.assertIn("top_proteins", data)
                    self.assertIn("binding_score", data)
                    print(f"✅ Prediction test passed for {smiles} on {organ}")
            
            except Exception as e:
                print(f"❌ Prediction test failed: {str(e)}")
                self.fail(f"Prediction test failed: {str(e)}")
    
    def test_05_predictions_by_analysis_id(self):
        """Test retrieving predictions by analysis ID"""
        print("\n🔍 Testing predictions retrieval by analysis ID...")
        
        # Skip if we don't have an analysis_id from the upload test
        if not self.analysis_id:
            print("⚠️ Skipping predictions retrieval test as no analysis_id is available")
            # Use a mock analysis_id for testing
            self.analysis_id = "00000000-0000-0000-0000-000000000000"
        
        try:
            response = requests.get(f"{self.api_url}/predictions/{self.analysis_id}")
            
            # We expect a 200 even if there are no predictions
            self.assertEqual(response.status_code, 200)
            data = response.json()
            
            # Data should be a list
            self.assertIsInstance(data, list)
            
            if len(data) > 0:
                # If we have predictions, check their structure
                prediction = data[0]
                self.assertIn("id", prediction)
                self.assertIn("analysis_id", prediction)
                self.assertIn("affected_genes", prediction)
                self.assertIn("potential_cures", prediction)
                self.assertIn("top_proteins", prediction)
                self.assertIn("binding_score", prediction)
            
            print(f"✅ Predictions retrieval test passed. Found {len(data)} predictions.")
        
        except Exception as e:
            print(f"❌ Predictions retrieval test failed: {str(e)}")
            self.fail(f"Predictions retrieval test failed: {str(e)}")

if __name__ == "__main__":
    unittest.main()
