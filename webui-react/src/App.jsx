import React from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { message } from 'antd'
import MainLayout from '@/layouts/MainLayout'
import Dashboard from '@/pages/Dashboard'
import Diagnosis from '@/pages/Diagnosis'
import Knowledge from '@/pages/Knowledge'
import KnowledgeChat from '@/pages/KnowledgeChat'
import Reports from '@/pages/Reports'
import Monitoring from '@/pages/Monitoring'
import Profile from '@/pages/Profile'
import Login from '@/pages/Login'
import { DiagnosisProvider } from '@/context/DiagnosisContext'

const ProtectedRoute = ({ children }) => {
  const location = useLocation()
  const token = localStorage.getItem('token')
  
  if (!token) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }
  
  return children
}

const AuthRoute = ({ children }) => {
  const token = localStorage.getItem('token')
  
  if (token) {
    return <Navigate to="/dashboard" replace />
  }
  
  return children
}

function App() {
  return (
    <DiagnosisProvider>
      <BrowserRouter
        future={{
          v7_startTransition: true,
          v7_relativeSplatPath: true
        }}
      >
        <Routes>
          <Route 
            path="/login" 
            element={
              <AuthRoute>
                <Login />
              </AuthRoute>
            } 
          />
          <Route 
            path="/" 
            element={
              <ProtectedRoute>
                <MainLayout />
              </ProtectedRoute>
            }
          >
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="dashboard" element={<Dashboard />} />
            <Route path="diagnosis" element={<Diagnosis />} />
            <Route path="knowledge" element={<Knowledge />} />
            <Route path="knowledge-chat" element={<KnowledgeChat />} />
            <Route path="reports" element={<Reports />} />
            <Route path="monitoring" element={<Monitoring />} />
            <Route path="profile" element={<Profile />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </DiagnosisProvider>
  )
}

export default App
