import { Database, FileEdit } from 'lucide-react';

export function Sidebar({ activePage, setActivePage }) {
  const navItems = [
    { id: 'crud', label: 'CRUD Operations', icon: FileEdit },
    { id: 'database', label: 'Database Architecture', icon: Database }
  ];

  return (
    <div className="w-64 bg-white border-r-2 border-cyan-400 shadow-xl p-6">
      {/* Logo/Header */}
      <div className="mb-8 pb-6 border-b-2 border-cyan-400">
        <h2 className="text-cyan-700 tracking-wider text-center">DISTRIBUTED DB</h2>
        <p className="text-xs text-slate-600 text-center mt-2">Management System</p>
      </div>

      {/* Navigation Items */}
      <nav className="space-y-3">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activePage === item.id;
          
          return (
            <button
              key={item.id}
              onClick={() => setActivePage(item.id)}
              className={`w-full flex items-center gap-3 px-4 py-3 transition-all border-2 ${
                isActive 
                  ? 'bg-cyan-100 border-cyan-600 text-cyan-800 shadow-md' 
                  : 'bg-white border-cyan-300 text-slate-700 hover:bg-cyan-50 hover:border-cyan-500'
              }`}
            >
              <Icon className={`w-5 h-5 ${isActive ? 'text-cyan-700' : 'text-slate-600'}`} />
              <span className={`text-sm tracking-wide ${isActive ? 'font-medium' : ''}`}>
                {item.label}
              </span>
            </button>
          );
        })}
      </nav>

      {/* Footer Info */}
      <div className="mt-auto pt-8 border-t-2 border-cyan-300 mt-12">
        <div className="text-xs text-slate-500 space-y-1">
          <p className="flex items-center gap-2">
            <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
            System Online
          </p>
          <p className="text-slate-400">v1.0.0</p>
        </div>
      </div>
    </div>
  );
}
