from proposal_generator import generate_proposals
props = generate_proposals('2025-12-14')
if props:
    p = props[0]
    print(f'Keys: {list(p.keys())}')
    print(f'top_results: {repr(p.get("top_results"))}')
