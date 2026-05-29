import { Outlet, NavLink } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { LayoutDashboard, Upload, Table2, LogOut } from 'lucide-react'

export default function Layout() {
  const { user, tenant, logout } = useAuth()

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <h1>Breathe ESG</h1>
          <span>{tenant?.name || 'No tenant'}</span>
        </div>

        <nav className="sidebar-nav">
          <NavLink to="/dashboard" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            <LayoutDashboard size={16} /> Dashboard
          </NavLink>
          <NavLink to="/upload" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            <Upload size={16} /> Upload Data
          </NavLink>
          <NavLink to="/records" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            <Table2 size={16} /> Review Records
          </NavLink>
        </nav>

        <div className="sidebar-footer">
          <div style={{ marginBottom: 8, color: 'rgba(255,255,255,.7)', fontWeight: 600 }}>
            {user?.username}
          </div>
          <div style={{ marginBottom: 8 }}>{tenant?.role}</div>
          <button
            onClick={logout}
            style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,.5)', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, padding: 0 }}
          >
            <LogOut size={13} /> Sign out
          </button>
        </div>
      </aside>

      <main className="main-content">
        <Outlet />
      </main>
    </div>
  )
}
