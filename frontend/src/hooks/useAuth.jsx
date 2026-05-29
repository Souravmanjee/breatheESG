import { createContext, useContext, useState, useEffect } from 'react'
import api from '../utils/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [tenant, setTenant] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('token')
    const savedTenant = localStorage.getItem('tenant')
    if (token && savedTenant) {
      setTenant(JSON.parse(savedTenant))
      api.get('/auth/me/').then(r => setUser(r.data.user)).catch(() => {
        localStorage.removeItem('token')
        localStorage.removeItem('tenant')
      }).finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [])

  const login = async (username, password) => {
    const r = await api.post('/auth/login/', { username, password })
    localStorage.setItem('token', r.data.token)
    setUser(r.data.user)
    // Auto-select first tenant
    const firstTenant = r.data.tenants[0]
    localStorage.setItem('tenant', JSON.stringify(firstTenant))
    setTenant(firstTenant)
    return r.data
  }

  const logout = async () => {
    try { await api.post('/auth/logout/') } catch {}
    localStorage.removeItem('token')
    localStorage.removeItem('tenant')
    setUser(null)
    setTenant(null)
  }

  return (
    <AuthContext.Provider value={{ user, tenant, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
