# Frontend Developer Guide

## 📋 Table of Contents
- [Overview](#overview)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Architecture](#architecture)
- [API Integration](#api-integration)
- [Component Guide](#component-guide)
- [Styling](#styling)
- [State Management](#state-management)
- [Common Tasks](#common-tasks)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

---

## 🎯 Overview

This is the frontend web application for a **Distributed Database System** with 3 nodes. The application provides:
- Real-time visualization of database nodes
- CRUD operations on distributed orders data
- Concurrency control testing and simulation
- System architecture visualization

### Database Architecture
- **Node 1 (Central)**: Contains complete orders dataset (master replica)
- **Node 2 (Fragment 1)**: Contains orders with even `order_id` values
- **Node 3 (Fragment 2)**: Contains orders with odd `order_id` values

---

## 🛠 Tech Stack

### Core Framework
- **React 18.3.1** - UI library with hooks and functional components
- **Vite 7.2.4** - Fast build tool and dev server

### Styling
- **Tailwind CSS 3.4.0** - Utility-first CSS framework
- **Framer Motion 11.15.0** - Animation library
- **Radix UI** - Accessible component primitives

### UI Components
- Pre-built component library in `src/components/ui/`
- Based on shadcn/ui architecture
- Fully customizable and accessible

### Icons
- **Lucide React** - Icon library

---

## 📁 Project Structure

```
frontend/web-app/
├── public/                    # Static assets
├── src/
│   ├── assets/               # Images, fonts, etc.
│   ├── components/           # React components
│   │   ├── ui/              # Reusable UI primitives (buttons, cards, etc.)
│   │   ├── DatabaseDashboard.jsx      # Main dashboard view
│   │   ├── ConcurrencyScenarios.jsx   # Concurrency testing UI
│   │   ├── SimplifiedArchitecture.jsx # Node visualization
│   │   └── ExampleAPIUsage.jsx        # API usage examples
│   ├── services/            # API service layer
│   │   └── api.js          # Centralized API functions
│   ├── App.jsx             # Root component
│   ├── main.jsx            # App entry point
│   └── index.css           # Global styles
├── .env.example            # Environment variables template
├── API_DOCS.md            # API endpoint documentation
├── DEVELOPER_GUIDE.md     # This file
├── package.json           # Dependencies
├── tailwind.config.js     # Tailwind configuration
└── vite.config.js         # Vite configuration
```

---

## 🚀 Getting Started

### Prerequisites
- **Node.js** 18+ and npm
- Backend API running on `http://localhost:3000`
- PostgreSQL databases (3 nodes) configured

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd frontend/web-app
   ```

2. **Install dependencies**
   ```bash
   npm install
   ```

3. **Configure environment variables**
   ```bash
   # Copy the example file
   cp .env.example .env
   
   # Edit .env and set your API URL
   VITE_API_URL=http://localhost:3000/api
   ```

4. **Start development server**
   ```bash
   npm run dev
   ```
   
   The app will be available at `http://localhost:5173` (or next available port)

5. **Build for production**
   ```bash
   npm run build
   npm run preview  # Preview production build
   ```

---

## 🏗 Architecture

### Component Hierarchy

```
App.jsx (Root)
├── Header (Database title & navigation)
└── Tabs
    ├── Dashboard Tab
    │   └── DatabaseDashboard.jsx
    │       ├── Node Status Cards
    │       ├── Orders Tables (Node 1, 2, 3)
    │       └── Refresh Controls
    ├── Concurrency Tab
    │   └── ConcurrencyScenarios.jsx
    │       ├── Scenario Cards
    │       └── Test Controls
    └── Architecture Tab
        └── SimplifiedArchitecture.jsx
            ├── Node Visualizations
            └── Architecture Diagrams
```

### Data Flow

```
User Action
    ↓
Component Event Handler
    ↓
API Service Function (src/services/api.js)
    ↓
HTTP Request to Backend
    ↓
Backend Response
    ↓
Component State Update
    ↓
UI Re-render
```

---

## 🔌 API Integration

### Centralized API Service

All backend communication goes through `src/services/api.js`. **Never use `fetch()` directly in components.**

#### Example Usage

```javascript
import { fetchAllOrders, createOrder } from '../services/api';

// In your component
const loadData = async () => {
  try {
    const orders = await fetchAllOrders();
    setOrders(orders); // { node1: [], node2: [], node3: [] }
  } catch (error) {
    console.error('Failed to load orders:', error);
  }
};

const addOrder = async (quantity, payload) => {
  try {
    const result = await createOrder({ quantity, payload });
    console.log('Created:', result);
  } catch (error) {
    console.error('Failed to create:', error);
  }
};
```

### Available API Functions

| Function | Purpose | Returns |
|----------|---------|---------|
| `fetchAllOrders()` | Get orders from all nodes | `{node1: [], node2: [], node3: []}` |
| `fetchOrdersFromNode(nodeId)` | Get orders from specific node | `{success, data}` |
| `createOrder(orderData)` | Create new order | `{success, data}` |
| `updateOrder(orderId, data)` | Update existing order | `{success, data}` |
| `deleteOrder(orderId)` | Delete order | `{success}` |
| `getAllNodeStatus()` | Check all node statuses | `{node1, node2, node3}` |
| `executeConcurrencyScenario(scenario, params)` | Run concurrency test | `{success, results}` |

See `API_DOCS.md` for complete endpoint documentation.

---

## 🧩 Component Guide

### Core Components

#### 1. **DatabaseDashboard.jsx**
Main dashboard showing live data from all 3 nodes.

**State:**
- `data`: Orders from all nodes
- `loading`: Loading state
- `error`: Error messages
- `nodeStatus`: Online/offline status

**Key Functions:**
- `fetchData()`: Loads orders from all nodes
- Auto-refreshes on mount

**Usage:**
```jsx
<DatabaseDashboard />
```

#### 2. **ConcurrencyScenarios.jsx**
Interactive concurrency testing interface.

**Props:**
- `activeScenario`: Currently selected scenario
- `setActiveScenario`: Update active scenario
- `isRunning`: Whether test is running
- `setIsRunning`: Update running state

**Scenarios:**
1. Concurrent Reads
2. Concurrent Writes
3. Read-Write Conflicts

**Usage:**
```jsx
<ConcurrencyScenarios 
  activeScenario={activeScenario}
  setActiveScenario={setActiveScenario}
  isRunning={isRunning}
  setIsRunning={setIsRunning}
/>
```

#### 3. **SimplifiedArchitecture.jsx**
Visual representation of the 3-node architecture.

**Features:**
- Animated node cards
- Real-time activity indicators
- Data flow visualization

**Usage:**
```jsx
<SimplifiedArchitecture 
  activeScenario={activeScenario}
  isRunning={isRunning}
/>
```

### UI Components (`src/components/ui/`)

Reusable, accessible components based on Radix UI:

- **Layout**: `Card`, `Separator`, `Accordion`
- **Forms**: `Button`, `Input`, `Textarea`, `Select`, `Checkbox`, `Switch`
- **Feedback**: `Alert`, `Badge`, `Progress`, `Skeleton`
- **Overlays**: `Dialog`, `Sheet`, `Popover`, `Tooltip`
- **Data**: `Table`, `Tabs`

**Import Example:**
```jsx
import { Button } from './ui/button';
import { Card, CardHeader, CardContent } from './ui/card';
import { Table, TableBody, TableRow, TableCell } from './ui/table';
```

---

## 🎨 Styling

### Tailwind CSS

The project uses Tailwind's utility-first approach.

**Common Patterns:**
```jsx
// Layout
<div className="flex items-center justify-between gap-4">

// Spacing
<div className="p-6 mx-auto mt-8">

// Colors
<div className="bg-cyan-50 text-cyan-900 border-cyan-200">

// Responsive
<div className="grid grid-cols-1 md:grid-cols-3 gap-6">

// Hover states
<button className="hover:bg-cyan-600 transition-colors">
```

### Custom Animations

Defined in `tailwind.config.js`:
- `gradient-shift`: Animated gradient backgrounds
- `shimmer`: Shimmer effect
- `pulse-glow`: Pulsing glow effect

**Usage:**
```jsx
<div className="animate-gradient-shift bg-gradient-to-r from-cyan-400 to-blue-500">
```

### Framer Motion

For complex animations:
```jsx
import { motion } from 'framer-motion';

<motion.div
  initial={{ opacity: 0, y: 20 }}
  animate={{ opacity: 1, y: 0 }}
  transition={{ duration: 0.3 }}
>
  Content
</motion.div>
```

---

## 🗂 State Management

### Local State (useState)

For component-specific data:
```jsx
const [orders, setOrders] = useState({ node1: [], node2: [], node3: [] });
const [loading, setLoading] = useState(false);
const [error, setError] = useState(null);
```

### Side Effects (useEffect)

For data fetching on mount:
```jsx
useEffect(() => {
  fetchData();
}, []); // Empty dependency array = run once on mount
```

### Lifting State Up

Shared state lives in `App.jsx` and is passed down:
```jsx
// In App.jsx
const [activeScenario, setActiveScenario] = useState(null);

// Pass to children
<ConcurrencyScenarios 
  activeScenario={activeScenario}
  setActiveScenario={setActiveScenario}
/>
```

---

## 📝 Common Tasks

### Adding a New Component

1. Create file in `src/components/`
   ```jsx
   export function MyComponent() {
     return <div>Hello</div>;
   }
   ```

2. Import in parent component
   ```jsx
   import { MyComponent } from './components/MyComponent';
   ```

### Adding a New API Endpoint

1. Add function to `src/services/api.js`
   ```javascript
   export const myNewEndpoint = async (params) => {
     return fetchAPI('/my-endpoint', {
       method: 'POST',
       body: JSON.stringify(params),
     });
   };
   ```

2. Use in component
   ```jsx
   import { myNewEndpoint } from '../services/api';
   
   const result = await myNewEndpoint({ data: 'test' });
   ```

### Creating a New Page/Tab

1. Create component file
2. Import in `App.jsx`
3. Add to `<Tabs>` component
   ```jsx
   <TabsList>
     <TabsTrigger value="mynewpage">My New Page</TabsTrigger>
   </TabsList>
   
   <TabsContent value="mynewpage">
     <MyNewComponent />
   </TabsContent>
   ```

### Adding Environment Variables

1. Add to `.env.example` (for documentation)
   ```
   VITE_MY_VAR=default_value
   ```

2. Add to your local `.env`
   ```
   VITE_MY_VAR=actual_value
   ```

3. Use in code
   ```javascript
   const myVar = import.meta.env.VITE_MY_VAR;
   ```

**Note:** Vite environment variables must start with `VITE_`

---

## ✅ Best Practices

### 1. **Always Use the API Service**
❌ Don't:
```javascript
const response = await fetch('http://localhost:3000/api/orders');
```

✅ Do:
```javascript
import { fetchAllOrders } from '../services/api';
const orders = await fetchAllOrders();
```

### 2. **Handle Loading & Error States**
```jsx
const [loading, setLoading] = useState(false);
const [error, setError] = useState(null);

const loadData = async () => {
  setLoading(true);
  setError(null);
  try {
    const data = await fetchAllOrders();
    setOrders(data);
  } catch (err) {
    setError(err.message);
  } finally {
    setLoading(false);
  }
};
```

### 3. **Keep Components Small**
- One component = one responsibility
- Extract reusable logic into custom hooks
- Split large components into smaller ones

### 4. **Use Consistent Naming**
- Components: `PascalCase` (e.g., `DatabaseDashboard`)
- Functions: `camelCase` (e.g., `fetchOrders`)
- Constants: `UPPER_CASE` (e.g., `API_BASE_URL`)
- Files: Match component name

### 5. **Comment Complex Logic**
```jsx
// Fetch orders from all nodes in parallel for better performance
const orders = await Promise.all([...]);
```

### 6. **Destructure Props**
```jsx
// Instead of props.value, props.onChange
export function MyComponent({ value, onChange, disabled = false }) {
  // ...
}
```

---

## 🐛 Troubleshooting

### Common Issues

#### 1. **"Cannot connect to backend"**
- Check if backend is running on `http://localhost:3000`
- Verify `VITE_API_URL` in `.env`
- Check CORS settings in backend

#### 2. **"Module not found" errors**
- Run `npm install`
- Delete `node_modules` and `package-lock.json`, then reinstall
- Check import paths are correct

#### 3. **Tailwind classes not working**
- Restart dev server (`Ctrl+C` then `npm run dev`)
- Check `tailwind.config.js` has correct content paths
- Verify class names are spelled correctly (no typos)

#### 4. **Components not updating**
- Check state is being updated correctly
- Verify `useEffect` dependencies are correct
- Use React DevTools to inspect component state

#### 5. **Port 5173 already in use**
- Vite will automatically use next available port (5174, 5175, etc.)
- Or manually kill the process using the port
- Check terminal output for actual port being used

### Debugging Tips

1. **Use React DevTools**
   - Install browser extension
   - Inspect component props and state
   - Track re-renders

2. **Console Logging**
   ```jsx
   console.log('Orders:', orders);
   console.log('Node status:', nodeStatus);
   ```

3. **Network Tab**
   - Check API requests in browser DevTools
   - Verify request/response format
   - Check for CORS errors

4. **Error Boundaries**
   - Wrap components in error boundaries for better error handling
   - Log errors to console or external service

---

## 📚 Additional Resources

### Documentation
- [React Docs](https://react.dev)
- [Vite Guide](https://vitejs.dev/guide/)
- [Tailwind CSS](https://tailwindcss.com/docs)
- [Framer Motion](https://www.framer.com/motion/)
- [Radix UI](https://www.radix-ui.com/)

### Project Files
- `API_DOCS.md` - Backend API endpoints
- `README.md` - Project overview
- `.env.example` - Environment variables reference

### Code Examples
- `src/components/ExampleAPIUsage.jsx` - API service usage patterns
- `src/components/DatabaseDashboard.jsx` - Full-featured component example

---

## 🤝 Contributing

### Before Starting Development

1. Pull latest changes from main branch
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes
4. Test thoroughly
5. Commit with descriptive messages
6. Push and create pull request

### Code Style

- Use **functional components** with hooks (no class components)
- Use **const** for components and functions
- Add **prop validation** when needed
- Keep **line length** under 100 characters when possible
- Use **meaningful variable names**

### Testing Checklist

- [ ] Component renders without errors
- [ ] All API calls work correctly
- [ ] Loading states display properly
- [ ] Error states are handled
- [ ] Responsive on mobile/tablet/desktop
- [ ] No console errors or warnings
- [ ] Follows existing code patterns

---

## 📞 Need Help?

If you're stuck:
1. Check this guide and `API_DOCS.md`
2. Review `ExampleAPIUsage.jsx` for patterns
3. Check existing components for similar functionality
4. Review browser console for errors
5. Check Network tab for API issues

---

**Last Updated:** November 30, 2025
**Version:** 1.0.0
