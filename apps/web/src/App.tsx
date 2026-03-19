import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import DealWorkspace from './pages/DealWorkspace'

export default function App() {
    return (
        <BrowserRouter>
            <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/deals/:dealId" element={<DealWorkspace />} />
            </Routes>
        </BrowserRouter>
    )
}
