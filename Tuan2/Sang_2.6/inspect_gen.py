import google.generativeai as gen
import inspect
print('gen version', getattr(gen, '__version__', 'unknown'))
print('has configure', hasattr(gen,'configure'))
print('has GenerativeModel', hasattr(gen,'GenerativeModel'))
if hasattr(gen,'GenerativeModel'):
    print('GenerativeModel attrs:', [a for a in dir(gen.GenerativeModel) if not a.startswith('_')])
    if hasattr(gen.GenerativeModel, 'generate_content'):
        print('generate_content sig:', inspect.signature(gen.GenerativeModel.generate_content))
    if hasattr(gen.GenerativeModel, 'start_chat'):
        print('start_chat sig:', inspect.signature(gen.GenerativeModel.start_chat))
