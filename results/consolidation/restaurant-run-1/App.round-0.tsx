import React, { useState, useEffect } from 'react';
import { 
  listInventoryItem, 
  createInventoryItem, 
  ApiError, 
  signOut, 
  listSupplier, 
  createSupplier, 
  listSupplierInvoice, 
  createSupplierInvoice,
  Row 
} from './api';

const App = () => {
  const [currentSection, setCurrentSection] = useState<'inventory_items' | 'suppliers' | 'supplier_invoices'>('inventory_items');
  const [inventoryItems, setInventoryItems] = useState<Row[]>([]);
  const [inventoryItemsLoading, setInventoryItemsLoading] = useState(true);
  const [inventoryItemsError, setInventoryItemsError] = useState<ApiError | null>(null);
  const [newInventoryItemTitle, setNewInventoryItemTitle] = useState('');

  const [suppliers, setSuppliers] = useState<Row[]>([]);
  const [suppliersLoading, setSuppliersLoading] = useState(true);
  const [suppliersError, setSuppliersError] = useState<ApiError | null>(null);
  const [newSupplierTitle, setNewSupplierTitle] = useState('');

  const [supplierInvoices, setSupplierInvoices] = useState<Row[]>([]);
  const [supplierInvoicesLoading, setSupplierInvoicesLoading] = useState(true);
  const [supplierInvoicesError, setSupplierInvoicesError] = useState<ApiError | null>(null);
  const [newSupplierInvoiceTitle, setNewSupplierInvoiceTitle] = useState('');

  useEffect(() => {
    if (currentSection === 'inventory_items') {
      loadInventoryItems();
    } else if (currentSection === 'suppliers') {
      loadSuppliers();
    } else if (currentSection === 'supplier_invoices') {
      loadSupplierInvoices();
    }
  }, [currentSection]);

  const loadInventoryItems = async () => {
    setInventoryItemsLoading(true);
    setInventoryItemsError(null);
    try {
      const items = await listInventoryItem();
      setInventoryItems(items);
    } catch (error) {
      if (error instanceof ApiError) {
        setInventoryItemsError(error);
      } else {
        setInventoryItemsError(new ApiError('Failed to load inventory items', 500));
      }
    } finally {
      setInventoryItemsLoading(false);
    }
  };

  const loadSuppliers = async () => {
    setSuppliersLoading(true);
    setSuppliersError(null);
    try {
      const items = await listSupplier();
      setSuppliers(items);
    } catch (error) {
      if (error instanceof ApiError) {
        setSuppliersError(error);
      } else {
        setSuppliersError(new ApiError('Failed to load suppliers', 500));
      }
    } finally {
      setSuppliersLoading(false);
    }
  };

  const loadSupplierInvoices = async () => {
    setSupplierInvoicesLoading(true);
    setSupplierInvoicesError(null);
    try {
      const items = await listSupplierInvoice();
      setSupplierInvoices(items);
    } catch (error) {
      if (error instanceof ApiError) {
        setSupplierInvoicesError(error);
      } else {
        setSupplierInvoicesError(new ApiError('Failed to load supplier invoices', 500));
      }
    } finally {
      setSupplierInvoicesLoading(false);
    }
  };

  const handleCreateInventoryItem = async () => {
    if (!newInventoryItemTitle.trim()) {
      setInventoryItemsError({ message: 'Title is required', status: 400 });
      return;
    }
    try {
      setInventoryItemsError(null);
      const newItem = await createInventoryItem(newInventoryItemTitle);
      setInventoryItems(prev => [...prev, newItem]);
      setNewInventoryItemTitle('');
    } catch (error) {
      if (error instanceof ApiError) {
        setInventoryItemsError(error);
      } else {
        setInventoryItemsError(new ApiError('Failed to create inventory item', 500));
      }
    }
  };

  const handleCreateSupplier = async () => {
    if (!newSupplierTitle.trim()) {
      setSuppliersError({ message: 'Title is required', status: 400 });
      return;
    }
    try {
      setSuppliersError(null);
      const newSupplier = await createSupplier(newSupplierTitle);
      setSuppliers(prev => [...prev, newSupplier]);
      setNewSupplierTitle('');
    } catch (error) {
      if (error instanceof ApiError) {
        setSuppliersError(error);
      } else {
        setSuppliersError(new ApiError('Failed to create supplier', 500));
      }
    }
  };

  const handleCreateSupplierInvoice = async () => {
    if (!newSupplierInvoiceTitle.trim()) {
      setSupplierInvoicesError({ message: 'Title is required', status: 400 });
      return;
    }
    try {
      setSupplierInvoicesError(null);
      const newInvoice = await createSupplierInvoice(newSupplierInvoiceTitle);
      setSupplierInvoices(prev => [...prev, newInvoice]);
      setNewSupplierInvoiceTitle('');
    } catch (error) {
      if (error instanceof ApiError) {
        setSupplierInvoicesError(error);
      } else {
        setSupplierInvoicesError(new ApiError('Failed to create supplier invoice', 500));
      }
    }
  };

  const renderSection = () => {
    switch (currentSection) {
      case 'inventory_items':
        return (
          <div 
            data-testid="inventory-item-list" 
            className="bg-white shadow-sm rounded-lg p-4"
          >
            {inventoryItemsLoading ? (
              <div className="text-center py-8 text-slate-500">Loading inventory items...</div>
            ) : inventoryItemsError ? (
              <div className="text-center py-8 text-red-500">
                Error: {inventoryItemsError.message}
              </div>
            ) : inventoryItems.length === 0 ? (
              <div className="text-center py-8 text-slate-500">
                No inventory items found
              </div>
            ) : (
              <div className="space-y-4">
                {inventoryItems.map(item => (
                  <div 
                    key={item.id} 
                    className="border rounded-md p-4 bg-slate-50"
                  >
                    {item.title}
                  </div>
                ))}
              </div>
            )}

            <div className="mt-4">
              <input
                type="text"
                value={newInventoryItemTitle}
                onChange={(e) => setNewInventoryItemTitle(e.target.value)}
                data-testid="inventory-item-title-input"
                placeholder="Add new inventory item"
                className="w-full p-2 border rounded-md focus:ring-2 focus:ring-blue-500 focus:outline-none"
              />
              <button
                onClick={handleCreateInventoryItem}
                data-testid="inventory-item-submit"
                className="mt-2 w-full sm:w-auto bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 transition-colors"
              >
                Add Inventory Item
              </button>
              {inventoryItemsError && (
                <div 
                  data-testid="inventory-item-form-error" 
                  className="mt-2 text-red-500 text-sm"
                >
                  {inventoryItemsError.message}
                </div>
              )}
            </div>
          </div>
        );
      case 'suppliers':
        return (
          <div 
            data-testid="supplier-list" 
            className="bg-white shadow-sm rounded-lg p-4"
          >
            {suppliersLoading ? (
              <div className="text-center py-8 text-slate-500">Loading suppliers...</div>
            ) : suppliersError ? (
              <div className="text-center py-8 text-red-500">
                Error: {suppliersError.message}
              </div>
            ) : suppliers.length === 0 ? (
              <div className="text-center py-8 text-slate-500">
                No suppliers found
              </div>
            ) : (
              <div className="space-y-4">
                {suppliers.map(item => (
                  <div 
                    key={item.id} 
                    className="border rounded-md p-4 bg-slate-50"
                  >
                    {item.title}
                  </div>
                ))}
              </div>
            )}

            <div className="mt-4">
              <input
                type="text"
                value={newSupplierTitle}
                onChange={(e) => setNewSupplierTitle(e.target.value)}
                data-testid="supplier-title-input"
                placeholder="Add new supplier"
                className="w-full p-2 border rounded-md focus:ring-2 focus:ring-blue-500 focus:outline-none"
              />
              <button
                onClick={handleCreateSupplier}
                data-testid="supplier-submit"
                className="mt-2 w-full sm:w-auto bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 transition-colors"
              >
                Add Supplier
              </button>
              {suppliersError && (
                <div 
                  data-testid="supplier-form-error" 
                  className="mt-2 text-red-500 text-sm"
                >
                  {suppliersError.message}
                </div>
              )}
            </div>
          </div>
        );
      case 'supplier_invoices':
        return (
          <div 
            data-testid="supplier-invoice-list" 
            className="bg-white shadow-sm rounded-lg p-4"
          >
            {supplierInvoicesLoading ? (
              <div className="text-center py-8 text-slate-500">Loading supplier invoices...</div>
            ) : supplierInvoicesError ? (
              <div className="text-center py-8 text-red-500">
                Error: {supplierInvoicesError.message}
              </div>
            ) : supplierInvoices.length === 0 ? (
              <div className="text-center py-8 text-slate-500">
                No supplier invoices found
              </div>
            ) : (
              <div className="space-y-4">
                {supplierInvoices.map(item => (
                  <div 
                    key={item.id} 
                    className="border rounded-md p-4 bg-slate-50"
                  >
                    {item.title}
                  </div>
                ))}
              </div>
            )}

            <div className="mt-4">
              <input
                type="text"
                value={newSupplierInvoiceTitle}
                onChange={(e) => setNewSupplierInvoiceTitle(e.target.value)}
                data-testid="supplier-invoice-title-input"
                placeholder="Add new supplier invoice"
                className="w-full p-2 border rounded-md focus:ring-2 focus:ring-blue-500 focus:outline-none"
              />
              <button
                onClick={handleCreateSupplierInvoice}
                data-testid="supplier-invoice-submit"
                className="mt-2 w-full sm:w-auto bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 transition-colors"
              >
                Add Supplier Invoice
              </button>
              {supplierInvoicesError && (
                <div 
                  data-testid="supplier-invoice-form-error" 
                  className="mt-2 text-red-500 text-sm"
                >
                  {supplierInvoicesError.message}
                </div>
              )}
            </div>
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white shadow-sm p-4">
        <div className="container mx-auto flex justify-between items-center">
          <h1 className="text-xl font-bold">Back of House</h1>
          <button
            data-testid="sign-out"
            onClick={async () => {
              await signOut();
            }}
            className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 transition-colors"
          >
            Sign Out
          </button>
        </div>
      </header>

      <main className="container mx-auto p-4">
        <div className="flex space-x-4 mb-4">
          <button
            data-testid="nav-inventory-item"
            onClick={() => setCurrentSection('inventory_items')}
            className={`p-2 rounded-md ${
              currentSection === 'inventory_items' 
                ? 'bg-blue-100 border-blue-500' 
                : 'bg-slate-100 border-slate-200'
            }`}
          >
            Inventory Items
          </button>
          <button
            data-testid="nav-supplier"
            onClick={() => setCurrentSection('suppliers')}
            className={`p-2 rounded-md ${
              currentSection === 'suppliers' 
                ? 'bg-blue-100 border-blue-500' 
                : 'bg-slate-100 border-slate-200'
            }`}
          >
            Suppliers
          </button>
          <button
            data-testid="nav-supplier-invoice"
            onClick={() => setCurrentSection('supplier_invoices')}
            className={`p-2 rounded-md ${
              currentSection === 'supplier_invoices' 
                ? 'bg-blue-100 border-blue-500' 
                : 'bg-slate-100 border-slate-200'
            }`}
          >
            Supplier Invoices
          </button>
        </div>

        {renderSection()}
      </main>
    </div>
  );
};

export default App;
