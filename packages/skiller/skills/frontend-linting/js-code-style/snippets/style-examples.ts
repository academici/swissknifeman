// Source: anonymized production Laravel project
// Examples «to/after» by key rules Spatie JS/TS-style.

// --- 1. const by default, let when reassigning, var never ---------

// Bad:
// var counter = 0;
// let config = { retries: 3 }; // is not reassigned - must be const

// Okay:
const config = { retries: 3 };
config.retries = 5; // property mutation under const is valid - the link does not change

let attempt = 0;
attempt += 1; // real reassignment - let justified

// --- 2. Strict === with explicit type cast ------------------------------

// Bad:
// if (input == 5) { ... }            // implicit cast
// if (count == null) { ... }

// Good: cast type explicitly BEFORE comparison
const number = parseInt(String(config.retries), 10);
if (number === 5) {
    // ...
}

// --- 3. function for named ones, arrows for callbacks ----------------

// Good: named function - via function, reads like a function
function saveUserSession(userSession: { id: number }) {
    return userSession.id;
}

// Good: callbacks and one-liners are arrows
const userSessions = [{ id: 1 }, { id: 2 }];
userSessions.forEach((s) => saveUserSession(s)); // short name is valid in a one-line arrow

// Bad: arrow function as named top-level function
// const saveUserSession = (userSession) => { ... };

// --- 4. Shorthand-object methods ------------------------------------------

// Okay:
const documentActions = {
    handleClick(event: Event) {
        // ...
    },
};

// Bad:
// const documentActions = {
//     handleClick: function (event) { ... },
// };

// --- 5. Destructuring instead of accessing by indexes/properties ------------

// Okay:
const [hours, minutes] = '12:00'.split(':');

// Good: object parameter with defaults
function createUser({ name, email, role = 'member' }: { name: string; email: string; role?: string }) {
    return { name, email, role };
}

// Bad:
// const parts = '12:00'.split(':');
// const hours = parts[0];
// const minutes = parts[1];

// --- 6. Full names in multiline functions ------------------------------

// Bad:
// function processDocs(ds) {
//     const res = [];
//     for (const d of ds) { res.push(d.id); }
//     return res;
// }

// Okay:
function processDocuments(documents: Array<{ id: number }>) {
    const documentIds = [];
    for (const document of documents) {
        documentIds.push(document.id);
    }
    return documentIds;
}

// --- 7. Named imports (tree-shaking) ----------------------------------

// Okay:
// import { ref, computed } from 'vue';
// import { show, store } from '@/actions/App/Http/Controllers/DocumentController';

// Bad:
// import * as Vue from 'vue';
// import DocumentController from '@/actions/App/Http/Controllers/DocumentController';

export { saveUserSession, createUser, processDocuments, documentActions, hours, minutes, attempt };
