import React, { useState, useCallback } from "react";
import "./App.css";
import axios from "axios";
import { useDropzone } from "react-dropzone";
import { 
  Upload, 
  FileText, 
  Dna, 
  TrendingUp, 
  AlertCircle, 
  CheckCircle, 
  Loader,
  Heart,
  Brain,
  Activity
} from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

function App() {
  const [uploadedFile, setUploadedFile] = useState(null);
  const [analysisId, setAnalysisId] = useState(null);
  const [fileInfo, setFileInfo] = useState(null);
  const [smiles, setSmiles] = useState("");
  const [organ, setOrgan] = useState("");
  const [prediction, setPrediction] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [step, setStep] = useState(1);

  // Common organs for dropdown
  const organs = [
    "liver", "lung", "heart", "brain", "kidney", 
    "muscle", "bone", "skin", "pancreas", "stomach"
  ];

  // Example SMILES for testing
  const exampleSmiles = [
    { name: "Aspirin", smiles: "CC(=O)OC1=CC=CC=C1C(=O)O" },
    { name: "Caffeine", smiles: "CN1C=NC2=C1C(=O)N(C(=O)N2C)C" },
    { name: "Ibuprofen", smiles: "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O" },
    { name: "Paracetamol", smiles: "CC(=O)NC1=CC=C(C=C1)O" }
  ];

  const onDrop = useCallback(async (acceptedFiles) => {
    const file = acceptedFiles[0];
    if (!file.name.endsWith('.h5ad')) {
      setError("Please upload a valid H5AD file");
      return;
    }

    setLoading(true);
    setError("");
    
    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await axios.post(`${API}/upload-h5ad`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      setUploadedFile(file);
      setAnalysisId(response.data.analysis_id);
      setFileInfo({
        filename: file.name,
        n_cells: response.data.n_cells,
        n_genes: response.data.n_genes
      });
      setStep(2);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to upload file");
    } finally {
      setLoading(false);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/octet-stream': ['.h5ad'] },
    multiple: false
  });

  const handlePrediction = async () => {
    if (!smiles || !organ || !analysisId) {
      setError("Please fill in all fields");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const response = await axios.post(`${API}/predict`, {
        smiles: smiles,
        organ: organ,
        analysis_id: analysisId
      });

      setPrediction(response.data);
      setStep(3);
    } catch (err) {
      setError(err.response?.data?.detail || "Prediction failed");
    } finally {
      setLoading(false);
    }
  };

  const resetAnalysis = () => {
    setUploadedFile(null);
    setAnalysisId(null);
    setFileInfo(null);
    setSmiles("");
    setOrgan("");
    setPrediction(null);
    setError("");
    setStep(1);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-indigo-50 to-purple-50">
      {/* Header */}
      <header className="bg-white shadow-lg border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-indigo-600 rounded-lg">
              <Dna className="h-8 w-8 text-white" />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-gray-900">
                scRNA-seq Ligand Effect Prediction
              </h1>
              <p className="text-gray-600 mt-1">
                Analyze ligand effects on gene expression in specific organs
              </p>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Progress Steps */}
        <div className="mb-8">
          <div className="flex items-center justify-center space-x-8">
            {[1, 2, 3].map((stepNum) => (
              <div key={stepNum} className="flex items-center">
                <div className={`flex items-center justify-center w-10 h-10 rounded-full border-2 
                  ${step >= stepNum ? 'bg-indigo-600 border-indigo-600 text-white' : 'border-gray-300 text-gray-500'}`}>
                  {stepNum}
                </div>
                <span className={`ml-2 text-sm font-medium 
                  ${step >= stepNum ? 'text-indigo-600' : 'text-gray-500'}`}>
                  {stepNum === 1 ? 'Upload Data' : stepNum === 2 ? 'Configure Analysis' : 'View Results'}
                </span>
                {stepNum < 3 && <div className="w-16 h-0.5 bg-gray-300 ml-4"></div>}
              </div>
            ))}
          </div>
        </div>

        {/* Error Display */}
        {error && (
          <div className="mb-6 bg-red-50 border border-red-200 rounded-lg p-4 flex items-center space-x-3">
            <AlertCircle className="h-5 w-5 text-red-500 flex-shrink-0" />
            <p className="text-red-700">{error}</p>
          </div>
        )}

        {/* Step 1: File Upload */}
        {step === 1 && (
          <div className="bg-white rounded-xl shadow-lg p-8">
            <div className="text-center mb-6">
              <h2 className="text-2xl font-bold text-gray-900 mb-2">Upload scRNA-seq Data</h2>
              <p className="text-gray-600">Upload your H5AD file containing single-cell RNA sequencing data</p>
            </div>

            <div
              {...getRootProps()}
              className={`border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-colors
                ${isDragActive ? 'border-indigo-500 bg-indigo-50' : 'border-gray-300 hover:border-indigo-400 hover:bg-gray-50'}`}
            >
              <input {...getInputProps()} />
              <Upload className="h-12 w-12 text-gray-400 mx-auto mb-4" />
              <p className="text-lg font-medium text-gray-900 mb-2">
                {isDragActive ? 'Drop the H5AD file here' : 'Drag & drop your H5AD file here'}
              </p>
              <p className="text-gray-500">or click to select a file</p>
              <p className="text-sm text-gray-400 mt-2">Supported format: .h5ad</p>
            </div>

            {loading && (
              <div className="mt-6 flex items-center justify-center space-x-3">
                <Loader className="h-5 w-5 animate-spin text-indigo-600" />
                <span className="text-gray-600">Processing file...</span>
              </div>
            )}
          </div>
        )}

        {/* Step 2: Configuration */}
        {step === 2 && (
          <div className="space-y-6">
            {/* File Info */}
            <div className="bg-white rounded-xl shadow-lg p-6">
              <div className="flex items-center space-x-3 mb-4">
                <CheckCircle className="h-6 w-6 text-green-500" />
                <h3 className="text-lg font-semibold text-gray-900">File Uploaded Successfully</h3>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 bg-gray-50 rounded-lg p-4">
                <div className="text-center">
                  <FileText className="h-8 w-8 text-indigo-600 mx-auto mb-2" />
                  <p className="text-sm font-medium text-gray-900">{fileInfo?.filename}</p>
                </div>
                <div className="text-center">
                  <Activity className="h-8 w-8 text-green-600 mx-auto mb-2" />
                  <p className="text-sm font-medium text-gray-900">{fileInfo?.n_cells} Cells</p>
                </div>
                <div className="text-center">
                  <TrendingUp className="h-8 w-8 text-purple-600 mx-auto mb-2" />
                  <p className="text-sm font-medium text-gray-900">{fileInfo?.n_genes} Genes</p>
                </div>
              </div>
            </div>

            {/* Configuration */}
            <div className="bg-white rounded-xl shadow-lg p-8">
              <h2 className="text-2xl font-bold text-gray-900 mb-6">Configure Analysis</h2>
              
              <div className="space-y-6">
                {/* SMILES Input */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Ligand SMILES String
                  </label>
                  <input
                    type="text"
                    value={smiles}
                    onChange={(e) => setSmiles(e.target.value)}
                    placeholder="Enter SMILES notation (e.g., CC(=O)OC1=CC=CC=C1C(=O)O)"
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                  />
                  
                  {/* Example SMILES */}
                  <div className="mt-3">
                    <p className="text-sm text-gray-600 mb-2">Quick examples:</p>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                      {exampleSmiles.map((example) => (
                        <button
                          key={example.name}
                          onClick={() => setSmiles(example.smiles)}
                          className="text-left p-2 text-xs bg-gray-100 hover:bg-gray-200 rounded border"
                        >
                          <div className="font-medium text-gray-900">{example.name}</div>
                          <div className="text-gray-600 truncate">{example.smiles}</div>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Organ Selection */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Target Organ
                  </label>
                  <select
                    value={organ}
                    onChange={(e) => setOrgan(e.target.value)}
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                  >
                    <option value="">Select target organ</option>
                    {organs.map((organName) => (
                      <option key={organName} value={organName}>
                        {organName.charAt(0).toUpperCase() + organName.slice(1)}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Action Buttons */}
                <div className="flex space-x-4 pt-4">
                  <button
                    onClick={handlePrediction}
                    disabled={!smiles || !organ || loading}
                    className="flex-1 bg-indigo-600 text-white py-3 px-6 rounded-lg font-semibold 
                      hover:bg-indigo-700 disabled:bg-gray-400 disabled:cursor-not-allowed
                      flex items-center justify-center space-x-2"
                  >
                    {loading ? (
                      <>
                        <Loader className="h-5 w-5 animate-spin" />
                        <span>Analyzing...</span>
                      </>
                    ) : (
                      <>
                        <Brain className="h-5 w-5" />
                        <span>Run Prediction</span>
                      </>
                    )}
                  </button>
                  <button
                    onClick={resetAnalysis}
                    className="px-6 py-3 border border-gray-300 text-gray-700 rounded-lg font-semibold hover:bg-gray-50"
                  >
                    Reset
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Step 3: Results */}
        {step === 3 && prediction && (
          <div className="space-y-6">
            {/* Summary Card */}
            <div className="bg-white rounded-xl shadow-lg p-8">
              <div className="flex items-center space-x-3 mb-6">
                <CheckCircle className="h-8 w-8 text-green-500" />
                <h2 className="text-2xl font-bold text-gray-900">Prediction Results</h2>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
                <div className="bg-gradient-to-r from-blue-50 to-blue-100 rounded-lg p-4">
                  <div className="flex items-center space-x-3">
                    <Heart className="h-8 w-8 text-blue-600" />
                    <div>
                      <p className="text-sm font-medium text-blue-800">Binding Score</p>
                      <p className="text-2xl font-bold text-blue-900">
                        {prediction.binding_score.toFixed(3)}
                      </p>
                    </div>
                  </div>
                </div>

                <div className="bg-gradient-to-r from-green-50 to-green-100 rounded-lg p-4">
                  <div className="flex items-center space-x-3">
                    <Dna className="h-8 w-8 text-green-600" />
                    <div>
                      <p className="text-sm font-medium text-green-800">Affected Genes</p>
                      <p className="text-2xl font-bold text-green-900">
                        {prediction.affected_genes.length}
                      </p>
                    </div>
                  </div>
                </div>

                <div className="bg-gradient-to-r from-purple-50 to-purple-100 rounded-lg p-4">
                  <div className="flex items-center space-x-3">
                    <TrendingUp className="h-8 w-8 text-purple-600" />
                    <div>
                      <p className="text-sm font-medium text-purple-800">Top Proteins</p>
                      <p className="text-2xl font-bold text-purple-900">
                        {prediction.top_proteins.length}
                      </p>
                    </div>
                  </div>
                </div>

                <div className="bg-gradient-to-r from-orange-50 to-orange-100 rounded-lg p-4">
                  <div className="flex items-center space-x-3">
                    <Activity className="h-8 w-8 text-orange-600" />
                    <div>
                      <p className="text-sm font-medium text-orange-800">Potential Cures</p>
                      <p className="text-2xl font-bold text-orange-900">
                        {prediction.potential_cures.length}
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              {/* Detailed Results */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                {/* Affected Genes */}
                <div className="bg-gray-50 rounded-lg p-6">
                  <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center space-x-2">
                    <Dna className="h-5 w-5 text-indigo-600" />
                    <span>Affected Genes</span>
                  </h3>
                  <div className="space-y-2">
                    {prediction.affected_genes.map((gene, index) => (
                      <div key={index} className="bg-white rounded px-3 py-2 text-sm font-mono">
                        {gene}
                      </div>
                    ))}
                  </div>
                </div>

                {/* Top Proteins */}
                <div className="bg-gray-50 rounded-lg p-6">
                  <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center space-x-2">
                    <TrendingUp className="h-5 w-5 text-purple-600" />
                    <span>Top Proteins</span>
                  </h3>
                  <div className="space-y-2">
                    {prediction.top_proteins.map((protein, index) => (
                      <div key={index} className="bg-white rounded px-3 py-2 text-sm font-mono">
                        {protein}
                      </div>
                    ))}
                  </div>
                </div>

                {/* Potential Cures */}
                <div className="bg-gray-50 rounded-lg p-6">
                  <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center space-x-2">
                    <Heart className="h-5 w-5 text-green-600" />
                    <span>Potential Disease Associations</span>
                  </h3>
                  <div className="space-y-2">
                    {prediction.potential_cures.map((cure, index) => (
                      <div key={index} className="bg-white rounded px-3 py-2 text-sm">
                        {cure}
                      </div>
                    ))}
                  </div>
                </div>

                {/* Analysis Info */}
                <div className="bg-gray-50 rounded-lg p-6">
                  <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center space-x-2">
                    <FileText className="h-5 w-5 text-blue-600" />
                    <span>Analysis Details</span>
                  </h3>
                  <div className="space-y-3 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-600">Target Organ:</span>
                      <span className="font-medium capitalize">{organ}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">Analysis ID:</span>
                      <span className="font-mono text-xs">{analysisId}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">SMILES:</span>
                      <span className="font-mono text-xs break-all">{smiles}</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex space-x-4 mt-8 pt-6 border-t border-gray-200">
                <button
                  onClick={resetAnalysis}
                  className="bg-indigo-600 text-white py-3 px-6 rounded-lg font-semibold hover:bg-indigo-700"
                >
                  New Analysis
                </button>
                <button
                  onClick={() => setStep(2)}
                  className="px-6 py-3 border border-gray-300 text-gray-700 rounded-lg font-semibold hover:bg-gray-50"
                >
                  Modify Parameters
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;