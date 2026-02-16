import { NavLink, Outlet } from 'react-router';

const navItems = [
  { to: '/workflows', label: 'Workflows' },
  { to: '/instances', label: 'Instances' },
  { to: '/connectors', label: 'Connectors' },
  { to: '/connections', label: 'Connections' },
];

export function Layout() {
  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-gray-900 text-white">
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center gap-6">
          <span className="font-semibold text-lg tracking-tight">Workflow Engine</span>
          <div className="flex gap-1">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded text-sm ${isActive ? 'bg-gray-700 text-white' : 'text-gray-300 hover:text-white'}`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </div>
        </div>
      </nav>
      <main className="max-w-6xl mx-auto px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
