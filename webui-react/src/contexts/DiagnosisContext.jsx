import React, { createContext, useContext, useReducer, useEffect, useCallback } from 'react';

const DiagnosisContext = createContext(null);

const STORAGE_KEY = 'diagnosis_state';

const initialState = {
  diagnosing: false,
  diagnosisId: null,
  uploadFile: null,
  diagnosisResult: null,
  terminalOutput: '',
  diagnosisProgress: 0,
  realTimeSteps: [],
  currentStepIndex: 0,
  startTime: null,
  endTime: null
};

function diagnosisReducer(state, action) {
  switch (action.type) {
    case 'START_DIAGNOSIS':
      return {
        ...state,
        diagnosing: true,
        diagnosisId: action.payload.diagnosisId,
        uploadFile: action.payload.uploadFile,
        startTime: Date.now(),
        endTime: null
      };
    case 'UPDATE_PROGRESS':
      return {
        ...state,
        diagnosisProgress: action.payload.progress,
        realTimeSteps: action.payload.steps || state.realTimeSteps,
        currentStepIndex: action.payload.currentStep || state.currentStepIndex
      };
    case 'UPDATE_TERMINAL':
      return {
        ...state,
        terminalOutput: action.payload.output
      };
    case 'COMPLETE_DIAGNOSIS':
      return {
        ...state,
        diagnosing: false,
        diagnosisResult: action.payload.result,
        diagnosisProgress: 100,
        endTime: Date.now()
      };
    case 'FAIL_DIAGNOSIS':
      return {
        ...state,
        diagnosing: false,
        endTime: Date.now()
      };
    case 'RESET_DIAGNOSIS':
      return {
        ...initialState
      };
    case 'RESTORE_STATE':
      return {
        ...action.payload
      };
    default:
      return state;
  }
}

export function DiagnosisProvider({ children }) {
  const [state, dispatch] = useReducer(diagnosisReducer, initialState, () => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed.diagnosing && parsed.startTime) {
          const elapsed = Date.now() - parsed.startTime;
          if (elapsed > 10 * 60 * 1000) {
            return initialState;
          }
        }
        return parsed;
      }
    } catch (e) {
      console.error('Failed to restore diagnosis state:', e);
    }
    return initialState;
  });

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (e) {
      console.error('Failed to save diagnosis state:', e);
    }
  }, [state]);

  const startDiagnosis = useCallback((diagnosisId, uploadFile) => {
    dispatch({
      type: 'START_DIAGNOSIS',
      payload: { diagnosisId, uploadFile }
    });
  }, []);

  const updateProgress = useCallback((progress, steps, currentStep) => {
    dispatch({
      type: 'UPDATE_PROGRESS',
      payload: { progress, steps, currentStep }
    });
  }, []);

  const updateTerminal = useCallback((output) => {
    dispatch({
      type: 'UPDATE_TERMINAL',
      payload: { output }
    });
  }, []);

  const completeDiagnosis = useCallback((result) => {
    dispatch({
      type: 'COMPLETE_DIAGNOSIS',
      payload: { result }
    });
  }, []);

  const failDiagnosis = useCallback(() => {
    dispatch({ type: 'FAIL_DIAGNOSIS' });
  }, []);

  const resetDiagnosis = useCallback(() => {
    dispatch({ type: 'RESET_DIAGNOSIS' });
    localStorage.removeItem(STORAGE_KEY);
  }, []);

  const value = {
    ...state,
    startDiagnosis,
    updateProgress,
    updateTerminal,
    completeDiagnosis,
    failDiagnosis,
    resetDiagnosis
  };

  return (
    <DiagnosisContext.Provider value={value}>
      {children}
    </DiagnosisContext.Provider>
  );
}

export function useDiagnosis() {
  const context = useContext(DiagnosisContext);
  if (!context) {
    throw new Error('useDiagnosis must be used within a DiagnosisProvider');
  }
  return context;
}

export default DiagnosisContext;
