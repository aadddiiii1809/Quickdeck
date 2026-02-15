"use client";

import { useEffect, useMemo, useState } from "react";

type AttributeDef = {
  code: string;
  label: string;
  required: boolean;
  inputType: "text" | "number" | "select";
  options?: string[];
};

type CategoryOption = {
  id: string;
  name: string;
  children?: CategoryOption[];
  attributes: AttributeDef[];
};

type Variant = {
  variantSku: string;
  size: string;
  color: string;
  quantity: number;
};

const CATEGORY_TREE: CategoryOption[] = [
  {
    id: "fashion",
    name: "Fashion",
    children: [
      {
        id: "womens-footwear",
        name: "Women Footwear",
        attributes: [
          { code: "material", label: "Material", required: true, inputType: "text" },
          { code: "toe_type", label: "Toe Type", required: true, inputType: "select", options: ["Round", "Pointed", "Open"] },
          { code: "heel_height", label: "Heel Height (cm)", required: false, inputType: "number" },
        ],
      },
      {
        id: "womens-kurtis",
        name: "Women Kurtis",
        attributes: [
          { code: "fabric", label: "Fabric", required: true, inputType: "text" },
          { code: "sleeve_length", label: "Sleeve Length", required: true, inputType: "select", options: ["Half", "Full", "3/4"] },
          { code: "fit", label: "Fit", required: false, inputType: "text" },
        ],
      },
    ],
    attributes: [],
  },
];

export default function CatalogMultiStepForm() {
  const [step, setStep] = useState(1);
  const [topCategory, setTopCategory] = useState("");
  const [leafCategory, setLeafCategory] = useState("");
  const [name, setName] = useState("");
  const [sku, setSku] = useState("");
  const [mrp, setMrp] = useState("");
  const [sellingPrice, setSellingPrice] = useState("");
  const [attributeValues, setAttributeValues] = useState<Record<string, string>>({});
  const [imageFiles, setImageFiles] = useState<File[]>([]);
  const [variants, setVariants] = useState<Variant[]>([{ variantSku: "", size: "", color: "", quantity: 0 }]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");

  const selectedTop = useMemo(() => CATEGORY_TREE.find((item) => item.id === topCategory), [topCategory]);
  const selectedLeaf = useMemo(() => selectedTop?.children?.find((item) => item.id === leafCategory), [selectedTop, leafCategory]);
  const dynamicAttributes = selectedLeaf?.attributes ?? [];
  const imagePreviews = useMemo(() => imageFiles.map((file) => URL.createObjectURL(file)), [imageFiles]);

  useEffect(() => {
    return () => {
      imagePreviews.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [imagePreviews]);

  const canGoStep2 = topCategory && leafCategory;
  const canGoStep3 = name && sku && mrp && sellingPrice;

  const updateVariant = (index: number, field: keyof Variant, value: string | number) => {
    setVariants((prev) => {
      const copy = [...prev];
      copy[index] = { ...copy[index], [field]: value };
      return copy;
    });
  };

  const addVariant = () => setVariants((prev) => [...prev, { variantSku: "", size: "", color: "", quantity: 0 }]);

  const validatePayload = (): string | null => {
    if (Number(sellingPrice) > Number(mrp)) return `Selling price (${sellingPrice}) cannot be greater than MRP (${mrp}).`;

    for (const attr of dynamicAttributes) {
      if (attr.required && !attributeValues[attr.code]) return `Please fill required field: ${attr.label}`;
    }

    return null;
  };

  const onSubmit = async () => {
    const message = validatePayload();
    if (message) {
      setError(message);
      return;
    }

    setError("");
    setIsSubmitting(true);

    try {
      const payload = {
        categoryId: leafCategory,
        name,
        sku,
        mrp: Number(mrp),
        sellingPrice: Number(sellingPrice),
        attributes: attributeValues,
        variants,
        imageNames: imageFiles.map((file) => file.name),
      };

      const response = await fetch("/api/catalog/single", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await response.json();
      if (!response.ok) throw new Error(data.error ?? "Unable to create catalog");

      setStep(1);
      setTopCategory("");
      setLeafCategory("");
      setName("");
      setSku("");
      setMrp("");
      setSellingPrice("");
      setAttributeValues({});
      setImageFiles([]);
      setVariants([{ variantSku: "", size: "", color: "", quantity: 0 }]);
    } catch (submitError) {
      const messageText = submitError instanceof Error ? submitError.message : "Something went wrong";
      setError(messageText);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-4xl rounded-2xl bg-white p-6 shadow-lg">
      <h1 className="text-2xl font-semibold text-slate-800">Create Catalog</h1>
      <p className="mt-1 text-sm text-slate-500">Step {step} of 4</p>
      {error ? <div className="mt-4 rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</div> : null}

      {step === 1 ? (
        <div className="mt-6 space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Category Group</label>
            <select className="w-full rounded-md border border-slate-300 px-3 py-2" value={topCategory} onChange={(event) => { setTopCategory(event.target.value); setLeafCategory(""); }}>
              <option value="">Select</option>
              {CATEGORY_TREE.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Sub Category</label>
            <select className="w-full rounded-md border border-slate-300 px-3 py-2" value={leafCategory} onChange={(event) => setLeafCategory(event.target.value)}>
              <option value="">Select</option>
              {(selectedTop?.children ?? []).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </div>
          <button className="rounded-md bg-slate-900 px-4 py-2 text-white disabled:bg-slate-300" disabled={!canGoStep2} onClick={() => setStep(2)}>Next</button>
        </div>
      ) : null}

      {step === 2 ? (
        <div className="mt-6 grid gap-4">
          <input className="rounded-md border border-slate-300 px-3 py-2" placeholder="Product Name" value={name} onChange={(event) => setName(event.target.value)} />
          <input className="rounded-md border border-slate-300 px-3 py-2" placeholder="SKU" value={sku} onChange={(event) => setSku(event.target.value)} />
          <input className="rounded-md border border-slate-300 px-3 py-2" placeholder="MRP" value={mrp} onChange={(event) => setMrp(event.target.value)} type="number" min={0} />
          <input className="rounded-md border border-slate-300 px-3 py-2" placeholder="Selling Price" value={sellingPrice} onChange={(event) => setSellingPrice(event.target.value)} type="number" min={0} />
          <div className="flex gap-2">
            <button className="rounded-md border border-slate-300 px-4 py-2" onClick={() => setStep(1)}>Back</button>
            <button className="rounded-md bg-slate-900 px-4 py-2 text-white disabled:bg-slate-300" disabled={!canGoStep3} onClick={() => setStep(3)}>Next</button>
          </div>
        </div>
      ) : null}

      {step === 3 ? (
        <div className="mt-6 space-y-4">
          <label className="block text-sm font-medium text-slate-700">Upload Images</label>
          <input type="file" accept="image/*" multiple onChange={(event) => setImageFiles(Array.from(event.target.files ?? []))} />
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">{imagePreviews.map((preview) => <img key={preview} src={preview} className="h-28 w-full rounded-md object-cover" alt="preview" />)}</div>
          <div className="space-y-3">
            <h2 className="text-sm font-semibold text-slate-700">Dynamic Attributes</h2>
            {dynamicAttributes.map((attr) => (
              <div key={attr.code}>
                <label className="mb-1 block text-sm text-slate-700">{attr.label}{attr.required ? " *" : ""}</label>
                {attr.inputType === "select" ? (
                  <select className="w-full rounded-md border border-slate-300 px-3 py-2" value={attributeValues[attr.code] ?? ""} onChange={(event) => setAttributeValues((prev) => ({ ...prev, [attr.code]: event.target.value }))}>
                    <option value="">Select</option>
                    {(attr.options ?? []).map((option) => <option key={option} value={option}>{option}</option>)}
                  </select>
                ) : (
                  <input type={attr.inputType} className="w-full rounded-md border border-slate-300 px-3 py-2" value={attributeValues[attr.code] ?? ""} onChange={(event) => setAttributeValues((prev) => ({ ...prev, [attr.code]: event.target.value }))} />
                )}
              </div>
            ))}
          </div>
          <div className="flex gap-2">
            <button className="rounded-md border border-slate-300 px-4 py-2" onClick={() => setStep(2)}>Back</button>
            <button className="rounded-md bg-slate-900 px-4 py-2 text-white" onClick={() => setStep(4)}>Next</button>
          </div>
        </div>
      ) : null}

      {step === 4 ? (
        <div className="mt-6 space-y-4">
          <h2 className="text-sm font-semibold text-slate-700">Variants</h2>
          <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
            <span className="font-medium">Price Check:</span> MRP: {mrp || "-"} | Selling Price: {sellingPrice || "-"}
          </div>
          <div className="hidden md:grid md:grid-cols-4 md:gap-3 px-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
            <span>Variant SKU</span>
            <span>Size</span>
            <span>Color</span>
            <span>Quantity</span>
          </div>
          {variants.map((variant, index) => (
            <div key={`${index}-${variant.variantSku}`} className="grid gap-3 rounded-md border border-slate-200 p-3 md:grid-cols-4">
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-600 md:hidden">Variant SKU</label>
                <input className="w-full rounded-md border border-slate-300 px-2 py-2" placeholder="Variant SKU" value={variant.variantSku} onChange={(event) => updateVariant(index, "variantSku", event.target.value)} />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-600 md:hidden">Size</label>
                <input className="w-full rounded-md border border-slate-300 px-2 py-2" placeholder="Size" value={variant.size} onChange={(event) => updateVariant(index, "size", event.target.value)} />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-600 md:hidden">Color</label>
                <input className="w-full rounded-md border border-slate-300 px-2 py-2" placeholder="Color" value={variant.color} onChange={(event) => updateVariant(index, "color", event.target.value)} />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-600 md:hidden">Quantity</label>
                <input className="w-full rounded-md border border-slate-300 px-2 py-2" placeholder="Quantity" type="number" min={0} value={variant.quantity} onChange={(event) => updateVariant(index, "quantity", Number(event.target.value))} />
              </div>
            </div>
          ))}
          <button className="rounded-md border border-slate-300 px-3 py-2" onClick={addVariant}>Add Variant</button>
          <div className="flex gap-2">
            <button className="rounded-md border border-slate-300 px-4 py-2" onClick={() => setStep(3)}>Back</button>
            <button className="rounded-md bg-emerald-600 px-4 py-2 text-white disabled:bg-emerald-300" disabled={isSubmitting} onClick={onSubmit}>{isSubmitting ? "Saving..." : "Submit Catalog"}</button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
