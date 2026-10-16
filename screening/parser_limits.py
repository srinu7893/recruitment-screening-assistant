"""OS-enforced limits for the isolated document parser."""
import os

_job = None


def apply():
    if os.name != 'nt':
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (90, 90))
        resource.setrlimit(resource.RLIMIT_FSIZE, (30 * 1024 * 1024,) * 2)
        return
    # Windows has no resource module. A Job Object limits this process and its
    # OCR children; the parent also enforces a wall-clock timeout.
    import ctypes
    from ctypes import wintypes as w

    class Basic(ctypes.Structure):
        _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                    ('flags', w.DWORD), ('min_working', ctypes.c_size_t),
                    ('max_working', ctypes.c_size_t), ('active', w.DWORD),
                    ('affinity', ctypes.c_size_t), ('priority', w.DWORD),
                    ('scheduling', w.DWORD)]

    class IO(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in
                    ('reads', 'writes', 'other', 'read_bytes', 'write_bytes', 'other_bytes')]

    class Extended(ctypes.Structure):
        _fields_ = [('basic', Basic), ('io', IO), ('process_memory', ctypes.c_size_t),
                    ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t),
                    ('peak_job', ctypes.c_size_t)]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
    kernel.CreateJobObjectW.restype = w.HANDLE
    kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
    kernel.SetInformationJobObject.restype = w.BOOL
    kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    kernel.AssignProcessToJobObject.restype = w.BOOL
    global _job
    _job = kernel.CreateJobObjectW(None, None)
    limits = Extended()
    limits.basic.flags = 0x2 | 0x200  # Per-process CPU time and total job memory.
    limits.basic.process_time = 90 * 10_000_000
    limits.job_memory = 768 * 1024 * 1024
    if not _job or not kernel.SetInformationJobObject(_job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        raise OSError('Cannot establish document parser limits')
    if not kernel.AssignProcessToJobObject(_job, kernel.GetCurrentProcess()):
        raise OSError('Cannot isolate document parser')
