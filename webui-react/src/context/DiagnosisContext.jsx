import React, { createContext, useContext, useReducer, useEffect, useCallback } from 'react';

const DiagnosisContext = createContext(null);

const STORAGE_KEY = 'diagnosis_global_state';

const initialState = {
  diagnosing: false,
  diagnosisProgress: 0,
  diagnosisResult: null,
  terminalOutput: '',
  realTimeSteps: [],
  currentStepIndex: 0,
  startTime: null,
  endTime: null,
  uploadFile: null,
  diagnosisId: null
};

function diagnosisReducer(state, action) {
  switch (action.type) {
    case 'START_DIAGNOSIS':
      return {
        ...state,
        diagnosing: true,
        diagnosisProgress: 0,
        diagnosisResult: null,
        terminalOutput: '',
        realTimeSteps: [],
        currentStepIndex: 0,
        startTime: Date.now(),
        endTime: null,
        uploadFile: action.payload.uploadFile,
        diagnosisId: action.payload.diagnosisId
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
      return initialState;
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

  // 安全序列化函数，处理循环引用和不可序列化的对象
  const safeStringify = (obj) => {
    const seen = new WeakSet();
    return JSON.stringify(obj, (key, value) => {
      // 跳过 File/Blob 对象
      if (value instanceof File || value instanceof Blob) {
        return value ? { name: value.name, size: value.size, type: value.type, _isFile: true } : null;
      }
      // 跳过循环引用
      if (typeof value === 'object' && value !== null) {
        if (seen.has(value)) {
          return '[Circular]';
        }
        seen.add(value);
      }
      // 跳过函数
      if (typeof value === 'function') {
        return undefined;
      }
      return value;
    });
  };

  useEffect(() => {
    try {
      const serialized = safeStringify(state);
      if (serialized) {
        localStorage.setItem(STORAGE_KEY, serialized);
      }
    } catch (e) {
      // 静默处理错误，不阻塞应用
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
    // 深拷贝结果对象，移除可能的循环引用
    const safeResult = JSON.parse(JSON.stringify(result, (key, value) => {
      if (key === 'uploadFile' || key === 'file') return null;
      return value;
    }));
    dispatch({
      type: 'COMPLETE_DIAGNOSIS',
      payload: { result: safeResult }
    });
  }, []);

  const failDiagnosis = useCallback(() => {
    dispatch({ type: 'FAIL_DIAGNOSIS' });
  }, []);

  const resetDiagnosis = useCallback(() => {
    dispatch({ type: 'RESET_DIAGNOSIS' });
  }, []);

  const { diagnosing, diagnosisProgress, diagnosisResult, terminalOutput, realTimeSteps, currentStepIndex, startTime, endTime, uploadFile, diagnosisId } = state;

  return (
    <DiagnosisContext.Provider value={{
      diagnosing,
      diagnosisProgress,
      diagnosisResult,
      terminalOutput,
      realTimeSteps,
      currentStepIndex,
      startTime,
      endTime,
      uploadFile,
      diagnosisId,
      startDiagnosis,
      updateProgress,
      updateTerminal,
      completeDiagnosis,
      failDiagnosis,
      resetDiagnosis
    }}>
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
