import * as XLSX from "xlsx";

export interface ParsedContact {
  name?: string;
  phone?: string;
  email?: string;
  notes?: string;
}

/**
 * Parses an Excel (.xlsx/.xls) or CSV file and extracts contact information.
 * Looks for common column headers such as Name, Phone, Contact, Email, Number, etc.
 */
export function parseExcelOrCsv(file: File): Promise<ParsedContact[]> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    
    reader.onload = (e) => {
      try {
        const data = e.target?.result;
        if (!data) {
          return resolve([]);
        }
        
        // Read the workbook as binary
        const workbook = XLSX.read(data, { type: "binary" });
        const firstSheetName = workbook.SheetNames[0];
        const worksheet = workbook.Sheets[firstSheetName];
        
        // Convert sheet to raw array of arrays or array of objects
        const rawRows = XLSX.utils.sheet_to_json<Record<string, any>>(worksheet);
        
        const contacts: ParsedContact[] = rawRows.map((row, index) => {
          // Find fields by searching for key substrings in case headers are styled differently
          const keys = Object.keys(row);
          
          let name = `Contact #${index + 1}`;
          let phone = "";
          let email = "";
          let notes = "";
          
          for (const key of keys) {
            if (row[key] === undefined || row[key] === null) continue;
            
            const normalizedKey = key.toString().toLowerCase().trim();
            const val = String(row[key]).trim();
            if (!val) continue;
            
            if (
              normalizedKey.includes("name") || 
              normalizedKey === "customer" || 
              normalizedKey === "lead" || 
              normalizedKey.includes("பெயர்")
            ) {
              name = val;
            } else if (
              normalizedKey.includes("phone") || 
              normalizedKey.includes("mobile") || 
              normalizedKey.includes("number") || 
              normalizedKey.includes("contact") ||
              normalizedKey === "tel" ||
              normalizedKey.includes("எண்") ||
              normalizedKey.includes("தொலைபேசி")
            ) {
              phone = val;
            } else if (normalizedKey.includes("email") || normalizedKey === "mail") {
              email = val;
            } else if (normalizedKey.includes("note") || normalizedKey.includes("detail") || normalizedKey.includes("remark") || normalizedKey.includes("குறிப்பு")) {
              notes = val;
            }
          }
          
          // If no specific phone number is detected, try to find any column containing numbers
          if (!phone) {
            for (const key of keys) {
              if (row[key] === undefined || row[key] === null) continue;
              const val = String(row[key]).trim();
              
              // Broad regex for phone number (at least 10 digits, allowing spaces, dashes, plus)
              const digitsOnly = val.replace(/\D/g, "");
              if (digitsOnly.length >= 9 && digitsOnly.length <= 15) {
                // If it looks like a phone number and isn't already assigned to another field
                if (val !== name && val !== email && val !== notes) {
                  phone = val;
                  break;
                }
              }
            }
          }
          
          return { name, phone, email, notes };
        });
        
        // Filter out contacts with empty phone numbers
        const validContacts = contacts.filter((c) => c.phone && c.phone.trim().length > 0);
        resolve(validContacts);
      } catch (err) {
        reject(err);
      }
    };
    
    reader.onerror = (err) => reject(err);
    reader.readAsBinaryString(file);
  });
}
