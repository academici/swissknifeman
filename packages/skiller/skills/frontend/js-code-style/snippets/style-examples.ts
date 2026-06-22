// Source: anonymized production Laravel project
// Примеры «до/после» по ключевым правилам Spatie JS/TS-стиля.

// --- 1. const по умолчанию, let при переприсваивании, var никогда ---------

// Плохо:
// var counter = 0;
// let config = { retries: 3 }; // не переприсваивается — должен быть const

// Хорошо:
const config = { retries: 3 };
config.retries = 5; // мутация свойства под const допустима — ссылка не меняется

let attempt = 0;
attempt += 1; // реальное переприсваивание — let оправдан

// --- 2. Строгое === с явным приведением типа ------------------------------

// Плохо:
// if (input == 5) { ... }            // неявное приведение
// if (count == null) { ... }

// Хорошо: привести тип явно ДО сравнения
const number = parseInt(String(config.retries), 10);
if (number === 5) {
    // ...
}

// --- 3. function для именованных, стрелочные для коллбеков ----------------

// Хорошо: именованная функция — через function, читается как функция
function saveUserSession(userSession: { id: number }) {
    return userSession.id;
}

// Хорошо: коллбеки и однострочники — стрелочные
const userSessions = [{ id: 1 }, { id: 2 }];
userSessions.forEach((s) => saveUserSession(s)); // короткое имя допустимо в однострочной стрелке

// Плохо: стрелочная функция как именованная top-level функция
// const saveUserSession = (userSession) => { ... };

// --- 4. Shorthand-методы объектов ------------------------------------------

// Хорошо:
const documentActions = {
    handleClick(event: Event) {
        // ...
    },
};

// Плохо:
// const documentActions = {
//     handleClick: function (event) { ... },
// };

// --- 5. Деструктуризация вместо обращения по индексам/свойствам ------------

// Хорошо:
const [hours, minutes] = '12:00'.split(':');

// Хорошо: параметр-объект с дефолтами
function createUser({ name, email, role = 'member' }: { name: string; email: string; role?: string }) {
    return { name, email, role };
}

// Плохо:
// const parts = '12:00'.split(':');
// const hours = parts[0];
// const minutes = parts[1];

// --- 6. Полные имена в многострочных функциях ------------------------------

// Плохо:
// function processDocs(ds) {
//     const res = [];
//     for (const d of ds) { res.push(d.id); }
//     return res;
// }

// Хорошо:
function processDocuments(documents: Array<{ id: number }>) {
    const documentIds = [];
    for (const document of documents) {
        documentIds.push(document.id);
    }
    return documentIds;
}

// --- 7. Именованные импорты (tree-shaking) ----------------------------------

// Хорошо:
// import { ref, computed } from 'vue';
// import { show, store } from '@/actions/App/Http/Controllers/DocumentController';

// Плохо:
// import * as Vue from 'vue';
// import DocumentController from '@/actions/App/Http/Controllers/DocumentController';

export { saveUserSession, createUser, processDocuments, documentActions, hours, minutes, attempt };
