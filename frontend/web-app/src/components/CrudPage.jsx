import { useState } from 'react';
import { Plus, Search, Edit, Trash2, Save, X } from 'lucide-react';

export function CrudPage() {
  const [users, setUsers] = useState([
    { id: 1, name: 'John Doe', email: 'john@example.com', role: 'Admin', node: 'Node 1' },
    { id: 2, name: 'Jane Smith', email: 'jane@example.com', role: 'User', node: 'Node 2' },
    { id: 3, name: 'Bob Johnson', email: 'bob@example.com', role: 'User', node: 'Node 3' },
  ]);
  
  const [isAdding, setIsAdding] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [formData, setFormData] = useState({ name: '', email: '', role: 'User', node: 'Node 1' });

  const handleCreate = () => {
    if (formData.name && formData.email) {
      setUsers([...users, { ...formData, id: Date.now() }]);
      setFormData({ name: '', email: '', role: 'User', node: 'Node 1' });
      setIsAdding(false);
    }
  };

  const handleUpdate = (id) => {
    setUsers(users.map(user => user.id === id ? { ...user, ...formData } : user));
    setEditingId(null);
    setFormData({ name: '', email: '', role: 'User', node: 'Node 1' });
  };

  const handleDelete = (id) => {
    setUsers(users.filter(user => user.id !== id));
  };

  const startEdit = (user) => {
    setEditingId(user.id);
    setFormData({ name: user.name, email: user.email, role: user.role, node: user.node });
  };

  const filteredUsers = users.filter(user => 
    user.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    user.email.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white border-2 border-cyan-400 shadow-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-2xl font-bold text-cyan-800">CRUD Operations</h2>
            <p className="text-sm text-slate-600 mt-1">Create, Read, Update, Delete user records</p>
          </div>
          <button
            onClick={() => setIsAdding(!isAdding)}
            className="flex items-center gap-2 px-6 py-3 bg-cyan-600 hover:bg-cyan-700 text-white border-2 border-cyan-700 shadow-md transition-all"
          >
            <Plus className="w-5 h-5" />
            <span>Create User</span>
          </button>
        </div>

        {/* Search Bar */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-slate-400" />
          <input
            type="text"
            placeholder="Search users by name or email..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-10 pr-4 py-3 border-2 border-cyan-300 focus:border-cyan-500 focus:outline-none bg-white text-slate-900"
          />
        </div>
      </div>

      {/* Create Form */}
      {isAdding && (
        <div className="bg-white border-2 border-green-400 shadow-lg p-6">
          <h3 className="text-lg font-bold text-green-800 mb-4">Create New User</h3>
          <div className="grid grid-cols-2 gap-4">
            <input
              type="text"
              placeholder="Name"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="px-4 py-2 border-2 border-slate-300 focus:border-green-500 focus:outline-none"
            />
            <input
              type="email"
              placeholder="Email"
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              className="px-4 py-2 border-2 border-slate-300 focus:border-green-500 focus:outline-none"
            />
            <select
              value={formData.role}
              onChange={(e) => setFormData({ ...formData, role: e.target.value })}
              className="px-4 py-2 border-2 border-slate-300 focus:border-green-500 focus:outline-none"
            >
              <option>User</option>
              <option>Admin</option>
            </select>
            <select
              value={formData.node}
              onChange={(e) => setFormData({ ...formData, node: e.target.value })}
              className="px-4 py-2 border-2 border-slate-300 focus:border-green-500 focus:outline-none"
            >
              <option>Node 1</option>
              <option>Node 2</option>
              <option>Node 3</option>
            </select>
          </div>
          <div className="flex gap-3 mt-4">
            <button
              onClick={handleCreate}
              className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white border-2 border-green-700"
            >
              <Save className="w-4 h-4" />
              Save
            </button>
            <button
              onClick={() => {
                setIsAdding(false);
                setFormData({ name: '', email: '', role: 'User', node: 'Node 1' });
              }}
              className="flex items-center gap-2 px-4 py-2 bg-slate-200 hover:bg-slate-300 text-slate-700 border-2 border-slate-300"
            >
              <X className="w-4 h-4" />
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Users Table */}
      <div className="bg-white border-2 border-cyan-400 shadow-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-cyan-100 border-b-2 border-cyan-400">
              <tr>
                <th className="px-6 py-4 text-left text-sm font-bold text-cyan-800 uppercase tracking-wider">ID</th>
                <th className="px-6 py-4 text-left text-sm font-bold text-cyan-800 uppercase tracking-wider">Name</th>
                <th className="px-6 py-4 text-left text-sm font-bold text-cyan-800 uppercase tracking-wider">Email</th>
                <th className="px-6 py-4 text-left text-sm font-bold text-cyan-800 uppercase tracking-wider">Role</th>
                <th className="px-6 py-4 text-left text-sm font-bold text-cyan-800 uppercase tracking-wider">Node</th>
                <th className="px-6 py-4 text-right text-sm font-bold text-cyan-800 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y-2 divide-slate-200">
              {filteredUsers.map((user) => (
                <tr key={user.id} className="hover:bg-cyan-50 transition-colors">
                  {editingId === user.id ? (
                    <>
                      <td className="px-6 py-4 text-sm text-slate-900">{user.id}</td>
                      <td className="px-6 py-4">
                        <input
                          type="text"
                          value={formData.name}
                          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                          className="w-full px-2 py-1 border-2 border-blue-400 focus:border-blue-600 focus:outline-none"
                        />
                      </td>
                      <td className="px-6 py-4">
                        <input
                          type="email"
                          value={formData.email}
                          onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                          className="w-full px-2 py-1 border-2 border-blue-400 focus:border-blue-600 focus:outline-none"
                        />
                      </td>
                      <td className="px-6 py-4">
                        <select
                          value={formData.role}
                          onChange={(e) => setFormData({ ...formData, role: e.target.value })}
                          className="w-full px-2 py-1 border-2 border-blue-400 focus:border-blue-600 focus:outline-none"
                        >
                          <option>User</option>
                          <option>Admin</option>
                        </select>
                      </td>
                      <td className="px-6 py-4">
                        <select
                          value={formData.node}
                          onChange={(e) => setFormData({ ...formData, node: e.target.value })}
                          className="w-full px-2 py-1 border-2 border-blue-400 focus:border-blue-600 focus:outline-none"
                        >
                          <option>Node 1</option>
                          <option>Node 2</option>
                          <option>Node 3</option>
                        </select>
                      </td>
                      <td className="px-6 py-4 text-right space-x-2">
                        <button
                          onClick={() => handleUpdate(user.id)}
                          className="px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white border-2 border-blue-700"
                        >
                          Save
                        </button>
                        <button
                          onClick={() => {
                            setEditingId(null);
                            setFormData({ name: '', email: '', role: 'User', node: 'Node 1' });
                          }}
                          className="px-3 py-1 bg-slate-200 hover:bg-slate-300 text-slate-700 border-2 border-slate-300"
                        >
                          Cancel
                        </button>
                      </td>
                    </>
                  ) : (
                    <>
                      <td className="px-6 py-4 text-sm text-slate-900 font-medium">{user.id}</td>
                      <td className="px-6 py-4 text-sm text-slate-900">{user.name}</td>
                      <td className="px-6 py-4 text-sm text-slate-600">{user.email}</td>
                      <td className="px-6 py-4">
                        <span className={`px-3 py-1 text-xs font-bold border-2 ${
                          user.role === 'Admin' 
                            ? 'bg-purple-100 border-purple-400 text-purple-800' 
                            : 'bg-blue-100 border-blue-400 text-blue-800'
                        }`}>
                          {user.role}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <span className="px-3 py-1 text-xs font-bold bg-cyan-100 border-2 border-cyan-400 text-cyan-800">
                          {user.node}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-right space-x-2">
                        <button
                          onClick={() => startEdit(user)}
                          className="p-2 bg-blue-100 hover:bg-blue-200 border-2 border-blue-400 text-blue-700 transition-colors"
                        >
                          <Edit className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleDelete(user.id)}
                          className="p-2 bg-red-100 hover:bg-red-200 border-2 border-red-400 text-red-700 transition-colors"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Stats Footer */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-white border-2 border-cyan-400 shadow-md p-4">
          <p className="text-sm text-slate-600 uppercase tracking-wide">Total Users</p>
          <p className="text-3xl font-bold text-cyan-700 mt-1">{users.length}</p>
        </div>
        <div className="bg-white border-2 border-purple-400 shadow-md p-4">
          <p className="text-sm text-slate-600 uppercase tracking-wide">Admins</p>
          <p className="text-3xl font-bold text-purple-700 mt-1">{users.filter(u => u.role === 'Admin').length}</p>
        </div>
        <div className="bg-white border-2 border-blue-400 shadow-md p-4">
          <p className="text-sm text-slate-600 uppercase tracking-wide">Regular Users</p>
          <p className="text-3xl font-bold text-blue-700 mt-1">{users.filter(u => u.role === 'User').length}</p>
        </div>
      </div>
    </div>
  );
}
