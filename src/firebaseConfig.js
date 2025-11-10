// --- Firebase Imports for Caching ---
import { initializeApp, getApp, getApps, setLogLevel } from "firebase/app";
import {
  getFirestore,
  doc,
  getDoc,
  setDoc,
  Timestamp,
} from "firebase/firestore";
import {
  getAuth,
  signInAnonymously,
  signInWithCustomToken,
  onAuthStateChanged,
} from "firebase/auth";

// --- Firebase Config ---
const firebaseConfig = {
  apiKey: "AIzaSyAT2jJAMMXErx-IAErqw5uvHaEbiVTh_js",
  authDomain: "nba-props-app-57fec.firebaseapp.com",
  projectId: "nba-props-app-57fec",
  storageBucket: "nba-props-app-57fec.firebasestorage.app",
  messagingSenderId: "139494696545",
  appId: "1:139494696545:web:004413270772fac564ac20",
  measurementId: "G-XE7KWJBH0Z",
};

// --- Firebase Initialization ---
let app;
let db;
let auth;

try {
  if (!getApps().length) {
    app = initializeApp(firebaseConfig);
  } else {
    app = getApp();
  }

  db = getFirestore(app);
  auth = getAuth(app);

  // Optional: Enable Firebase debug logs
  // setLogLevel("debug");
} catch (e) {
  console.error("Firebase initialization error:", e);
}

export { app, db, auth };
